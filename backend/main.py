import asyncio
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import urllib.request
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

try:
    from .auth import (
        create_session,
        hash_password,
        hash_session_token,
        verify_password,
    )
    from .cycle import build_calendar
    from .database import get_connection, init_db, row_to_log, row_to_user
    from .schemas import (
        AuthResponse,
        DailyLog,
        DailyLogCreate,
        Period,
        PeriodCreate,
        PeriodUpdate,
        UserLogin,
        UserRegister,
    )
except ImportError:
    from auth import create_session, hash_password, hash_session_token, verify_password
    from cycle import build_calendar
    from database import get_connection, init_db, row_to_log, row_to_user
    from schemas import (
        AuthResponse,
        DailyLog,
        DailyLogCreate,
        Period,
        PeriodCreate,
        PeriodUpdate,
        UserLogin,
        UserRegister,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_ORIGINS = (
    "https://diaaap.github.io,http://127.0.0.1:8000,http://localhost:8000"
)
logger = logging.getLogger("uvicorn.error")
bearer_scheme = HTTPBearer(auto_error=False)


def ollama_is_running() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def start_ollama() -> subprocess.Popen | None:
    if os.getenv("SANA_START_OLLAMA", "1") == "0":
        logger.info("Automatic Ollama startup is disabled")
        return None
    if ollama_is_running():
        logger.info("Ollama is already running; Sana will use the existing process")
        return None

    executable = shutil.which("ollama")
    if executable is None:
        logger.warning("Ollama was not found; AI chat will stay offline")
        return None

    environment = os.environ.copy()
    environment.setdefault("OLLAMA_ORIGINS", OLLAMA_ORIGINS)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    logger.info("Starting Ollama together with Sana")
    return subprocess.Popen(
        [executable, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        creationflags=creation_flags,
    )


def stop_ollama(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    logger.info("Stopping the Ollama process started by Sana")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ollama_process = start_ollama()
    if ollama_process is not None:
        for _ in range(40):
            if ollama_is_running() or ollama_process.poll() is not None:
                break
            await asyncio.sleep(0.25)
    try:
        yield
    finally:
        stop_ollama(ollama_process)


app = FastAPI(
    title="Sana Health Tracker API",
    description="API for accounts, daily wellbeing and personal cycle records.",
    version="0.2.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def disable_frontend_cache(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    token_hash = hash_session_token(credentials.credentials)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if row is None:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
            raise HTTPException(status_code=401, detail="Session is invalid or expired")
    return row_to_user(row)


def require_user(user: dict | None = Depends(get_optional_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def owner_filter(user: dict | None) -> tuple[str, tuple]:
    if user is None:
        return "user_id IS NULL", ()
    return "user_id = ?", (user["id"],)


def issue_session(connection: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    token, token_hash, expires_at = create_session()
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires_at),
    )
    return token, expires_at


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "sana-api"}


@app.post(
    "/api/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: UserRegister):
    email = str(payload.email).lower()
    password_hash = hash_password(payload.password.get_secret_value())

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (payload.name, email, password_hash),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            token, expires_at = issue_session(connection, cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error

    if row is None:
        raise HTTPException(status_code=500, detail="User was not created")
    return {
        "message": "Registration successful",
        "user": row_to_user(row),
        "token": token,
        "expires_at": expires_at,
    }


@app.post("/api/auth/login", response_model=AuthResponse)
def login_user(payload: UserLogin):
    email = str(payload.email).lower()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

    if row is None or not verify_password(
        payload.password.get_secret_value(), row["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE user_id = ? AND expires_at <= ?",
            (row["id"], datetime.now(timezone.utc).isoformat()),
        )
        token, expires_at = issue_session(connection, row["id"])
    return {
        "message": "Login successful",
        "user": row_to_user(row),
        "token": token,
        "expires_at": expires_at,
    }


@app.get("/api/auth/me")
def current_user(user: dict = Depends(require_user)) -> dict:
    return user


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    _: dict = Depends(require_user),
) -> Response:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (hash_session_token(credentials.credentials),),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/logs", response_model=list[DailyLog])
def list_logs(
    limit: int = Query(default=30, ge=1, le=100),
    user: dict | None = Depends(get_optional_user),
):
    where, params = owner_filter(user)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM daily_logs WHERE {where} "
            "ORDER BY entry_date DESC, id DESC LIMIT ?",
            params + (limit,),
        ).fetchall()
    return [row_to_log(row) for row in rows]


@app.post("/api/logs", response_model=DailyLog, status_code=status.HTTP_201_CREATED)
def create_log(
    payload: DailyLogCreate,
    user: dict | None = Depends(get_optional_user),
):
    where, owner_params = owner_filter(user)
    user_id = user["id"] if user else None
    with get_connection() as connection:
        existing = connection.execute(
            f"SELECT id FROM daily_logs WHERE entry_date = ? AND {where} "
            "ORDER BY id DESC LIMIT 1",
            (payload.entry_date.isoformat(),) + owner_params,
        ).fetchone()
        values = (
            payload.mood,
            payload.energy,
            json.dumps(payload.symptoms, ensure_ascii=False),
            payload.notes,
        )
        if existing:
            connection.execute(
                """
                UPDATE daily_logs
                SET mood = ?, energy = ?, symptoms = ?, notes = ?
                WHERE id = ?
                """,
                values + (existing["id"],),
            )
            log_id = existing["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO daily_logs
                    (entry_date, mood, energy, symptoms, notes, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.entry_date.isoformat(),) + values + (user_id,),
            )
            log_id = cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM daily_logs WHERE id = ?", (log_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Log was not saved")
    return row_to_log(row)


@app.delete("/api/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    log_id: int,
    user: dict | None = Depends(get_optional_user),
) -> Response:
    where, params = owner_filter(user)
    with get_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM daily_logs WHERE id = ? AND {where}", (log_id,) + params
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Log was not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/periods", response_model=list[Period])
def list_periods(user: dict | None = Depends(get_optional_user)):
    where, params = owner_filter(user)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM periods WHERE {where} "
            "ORDER BY start_date DESC, id DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/periods", response_model=Period, status_code=status.HTTP_201_CREATED)
def create_period(
    payload: PeriodCreate,
    user: dict | None = Depends(get_optional_user),
):
    where, owner_params = owner_filter(user)
    user_id = user["id"] if user else None
    with get_connection() as connection:
        start_date = payload.start_date.isoformat()
        end_date = payload.end_date.isoformat() if payload.end_date else None
        existing = connection.execute(
            f"SELECT id FROM periods WHERE start_date = ? AND {where} "
            "ORDER BY id DESC LIMIT 1",
            (start_date,) + owner_params,
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE periods SET end_date = ? WHERE id = ?",
                (end_date, existing["id"]),
            )
            period_id = existing["id"]
        else:
            cursor = connection.execute(
                "INSERT INTO periods (start_date, end_date, user_id) VALUES (?, ?, ?)",
                (start_date, end_date, user_id),
            )
            period_id = cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM periods WHERE id = ?", (period_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Period was not saved")
    return dict(row)


@app.patch("/api/periods/{period_id}", response_model=Period)
def update_period(
    period_id: int,
    payload: PeriodUpdate,
    user: dict | None = Depends(get_optional_user),
):
    where, params = owner_filter(user)
    with get_connection() as connection:
        current = connection.execute(
            f"SELECT * FROM periods WHERE id = ? AND {where}",
            (period_id,) + params,
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Period was not found")
        if payload.end_date and payload.end_date < date.fromisoformat(
            current["start_date"]
        ):
            raise HTTPException(
                status_code=422,
                detail="end_date cannot be earlier than start_date",
            )
        connection.execute(
            "UPDATE periods SET end_date = ? WHERE id = ?",
            (payload.end_date.isoformat() if payload.end_date else None, period_id),
        )
        row = connection.execute(
            "SELECT * FROM periods WHERE id = ?", (period_id,)
        ).fetchone()
    return dict(row)


@app.delete("/api/periods/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_period(
    period_id: int,
    user: dict | None = Depends(get_optional_user),
) -> Response:
    where, params = owner_filter(user)
    with get_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM periods WHERE id = ? AND {where}", (period_id,) + params
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Period was not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/calendar")
def get_calendar(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    user: dict | None = Depends(get_optional_user),
):
    current_date = date.today()
    where, params = owner_filter(user)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM periods WHERE {where} ORDER BY start_date, id", params
        ).fetchall()
    return build_calendar(rows, year or current_date.year, month or current_date.month)


@app.get("/api/summary")
def get_summary(user: dict | None = Depends(get_optional_user)) -> dict:
    where, params = owner_filter(user)
    with get_connection() as connection:
        log_rows = connection.execute(
            f"SELECT * FROM daily_logs WHERE {where} ORDER BY entry_date", params
        ).fetchall()
        period_rows = connection.execute(
            f"SELECT * FROM periods WHERE {where} ORDER BY start_date", params
        ).fetchall()

    logs = [row_to_log(row) for row in log_rows]
    mood_counts = Counter(log["mood"] for log in logs)
    energy_counts = Counter(log["energy"] for log in logs)
    symptom_counts = Counter(
        symptom
        for log in logs
        for symptom in log["symptoms"]
        if symptom != "none"
    )
    calendar = build_calendar(period_rows, date.today().year, date.today().month)
    return {
        "logs_count": len(logs),
        "periods_count": len(period_rows),
        "first_log_date": logs[0]["entry_date"] if logs else None,
        "latest_log_date": logs[-1]["entry_date"] if logs else None,
        "mood_counts": dict(mood_counts),
        "energy_counts": dict(energy_counts),
        "symptom_counts": dict(symptom_counts.most_common()),
        "cycle_length": calendar["cycle_length"] if calendar["has_data"] else None,
        "period_length": calendar["period_length"] if calendar["has_data"] else None,
        "current_phase": calendar["current_phase"],
        "status": "ready" if logs and period_rows else "needs_more_data",
    }


@app.delete("/api/data", status_code=status.HTTP_204_NO_CONTENT)
def clear_tracker_data(
    user: dict | None = Depends(get_optional_user),
) -> Response:
    where, params = owner_filter(user)
    with get_connection() as connection:
        connection.execute(f"DELETE FROM daily_logs WHERE {where}", params)
        connection.execute(f"DELETE FROM periods WHERE {where}", params)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
