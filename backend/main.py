import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.staticfiles import StaticFiles

try:
    from .auth import hash_password, verify_password
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sana Health Tracker API",
    description="Minimal API for daily wellbeing and cycle records.",
    version="0.1.0",
    lifespan=lifespan,
)


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
        cursor = connection.execute(
            """
            INSERT INTO daily_logs (entry_date, mood, energy, symptoms, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload.entry_date.isoformat(),
                payload.mood,
                payload.energy,
                json.dumps(payload.symptoms, ensure_ascii=False),
                payload.notes,
            ),
        )
        row = connection.execute(
            "SELECT * FROM daily_logs WHERE id = ?", (cursor.lastrowid,)
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
        cursor = connection.execute(
            "INSERT INTO periods (start_date, end_date) VALUES (?, ?)",
            (
                payload.start_date.isoformat(),
                payload.end_date.isoformat() if payload.end_date else None,
            ),
        )
        row = connection.execute(
            "SELECT * FROM periods WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Period was not saved")
    return dict(row)


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
