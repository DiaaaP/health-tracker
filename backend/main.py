import asyncio
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import urllib.request
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.staticfiles import StaticFiles

try:
    from .auth import hash_password, verify_password
    from .cycle import build_calendar
    from .database import get_connection, init_db, row_to_log, row_to_user
    from .schemas import (
        AuthResponse,
        DailyLog,
        DailyLogCreate,
        Period,
        PeriodCreate,
        UserLogin,
        UserRegister,
    )
except ImportError:
    from auth import hash_password, verify_password
    from cycle import build_calendar
    from database import get_connection, init_db, row_to_log, row_to_user
    from schemas import (
        AuthResponse,
        DailyLog,
        DailyLogCreate,
        Period,
        PeriodCreate,
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


def ollama_is_running() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def start_ollama() -> subprocess.Popen | None:
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
    description="Minimal API for daily wellbeing and cycle records.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def disable_frontend_cache(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


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
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error

    if row is None:
        raise HTTPException(status_code=500, detail="User was not created")
    return {"message": "Registration successful", "user": row_to_user(row)}


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
    return {"message": "Login successful", "user": row_to_user(row)}


@app.get("/api/logs", response_model=list[DailyLog])
def list_logs(limit: int = Query(default=30, ge=1, le=100)):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM daily_logs ORDER BY entry_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_log(row) for row in rows]


@app.post("/api/logs", response_model=DailyLog, status_code=status.HTTP_201_CREATED)
def create_log(payload: DailyLogCreate):
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM daily_logs WHERE entry_date = ? ORDER BY id DESC LIMIT 1",
            (payload.entry_date.isoformat(),),
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
                INSERT INTO daily_logs (entry_date, mood, energy, symptoms, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.entry_date.isoformat(),) + values,
            )
            log_id = cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM daily_logs WHERE id = ?", (log_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Log was not saved")
    return row_to_log(row)


@app.get("/api/periods", response_model=list[Period])
def list_periods():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM periods ORDER BY start_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/periods", response_model=Period, status_code=status.HTTP_201_CREATED)
def create_period(payload: PeriodCreate):
    with get_connection() as connection:
        start_date = payload.start_date.isoformat()
        end_date = payload.end_date.isoformat() if payload.end_date else None
        existing = connection.execute(
            "SELECT id FROM periods WHERE start_date = ? ORDER BY id DESC LIMIT 1",
            (start_date,),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE periods SET end_date = ? WHERE id = ?",
                (end_date, existing["id"]),
            )
            period_id = existing["id"]
        else:
            cursor = connection.execute(
                "INSERT INTO periods (start_date, end_date) VALUES (?, ?)",
                (start_date, end_date),
            )
            period_id = cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM periods WHERE id = ?", (period_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Period was not saved")
    return dict(row)


@app.delete("/api/periods/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_period(period_id: int) -> Response:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM periods WHERE id = ?", (period_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Period was not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/calendar")
def get_calendar(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
):
    current_date = date.today()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM periods ORDER BY start_date, id"
        ).fetchall()
    return build_calendar(rows, year or current_date.year, month or current_date.month)


@app.get("/api/summary")
def get_summary() -> dict[str, int | str]:
    """Basic summary; the team can extend it with real cycle calculations."""
    with get_connection() as connection:
        logs_count = connection.execute(
            "SELECT COUNT(*) FROM daily_logs"
        ).fetchone()[0]
        periods_count = connection.execute(
            "SELECT COUNT(*) FROM periods"
        ).fetchone()[0]
    return {
        "logs_count": logs_count,
        "periods_count": periods_count,
        "status": "basic",
    }


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
