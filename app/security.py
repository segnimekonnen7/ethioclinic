"""
Password hashing and JWT token utilities.

We use bcrypt for password hashing (via passlib) because it's slow and
deliberately hard to attack with GPUs — a single guess takes milliseconds,
not nanoseconds. For JWTs, we use HS256 and sign with a secret from the
environment.
"""

import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

# CryptContext is passlib's password hashing abstraction. Using "bcrypt"
# scheme means we hash with bcrypt and can verify against bcrypt hashes.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Read the JWT signing secret from the environment. In a real system this
# would be a long random string stored in a secrets vault.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = 60


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt. Always call this before
    storing a password — never store plaintext.
    """
    return pwd_context.hash(password)


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Check if a plaintext password matches a stored bcrypt hash.
    passlib handles the comparison safely (timing-attack resistant).
    """
    return pwd_context.verify(plaintext, hashed)


def create_access_token(user_id: int, role: str, expires_in_minutes: int = JWT_EXPIRY_MINUTES) -> str:
    """
    Create a JWT access token. The payload includes:
      - sub: the user ID (standard claim for "subject")
      - role: the user's role (for quick authorization checks)
      - exp: when the token expires (standard claim)

    The token is signed with HS256 using JWT_SECRET from the environment.
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=expires_in_minutes)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expires_at,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT. Raises JWTError if:
      - the signature is invalid (someone tampered with it)
      - it has expired
      - it's malformed

    Returns the payload dict if valid.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        # We raise so the caller can catch and return 401.
        raise
