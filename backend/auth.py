import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SESSION_DAYS = 30


def hash_password(password: str) -> str:
    """Create a salted password hash suitable for storing in SQLite."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        ITERATIONS,
    ).hex()
    return f"{ALGORITHM}${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a password without exposing the stored hash."""
    try:
        algorithm, iterations, salt, expected_digest = stored_hash.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual_digest, expected_digest)


def create_session() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    return token, token_hash, expires_at.isoformat()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
