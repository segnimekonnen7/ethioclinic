"""
Authentication routes: signup and login.

These are the gateway to the system. Signup creates a User with a hashed
password and patient role by default. Login verifies the credentials and
returns a JWT token.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, Role
from app.schemas import SignupRequest, LoginRequest, AccessTokenResponse, UserResponse
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    """
    Create a new user account.

    Email must be unique — the database enforces this with a UNIQUE constraint.
    If someone tries to register with an email that already exists, SQLAlchemy
    will raise an IntegrityError, which FastAPI converts to a 409 Conflict.

    We hash the password with bcrypt before storing it. The plaintext password
    is never written to disk.
    """

    # Check if email already exists (optional, but gives a cleaner error message).
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {req.email} already registered",
        )

    # Hash the password. This is slow (by design) — about 150ms per hash
    # on modern hardware. That's fine for signup (once per user).
    hashed = hash_password(req.password)

    # Create the user with a default role of 'patient'.
    user = User(
        email=req.email,
        pw_hash=hashed,
        role=Role.patient,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=AccessTokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Log in with email and password.

    We verify the password against the stored bcrypt hash, then issue a JWT
    token that the client can use for subsequent requests.

    Returns 401 Unauthorized if the email doesn't exist or the password is wrong.
    We don't distinguish between the two (good security practice — don't leak
    whether an email is registered).
    """

    user = db.query(User).filter(User.email == req.email).first()

    if not user or not verify_password(req.password, user.pw_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Create a JWT token with user ID and role.
    token = create_access_token(user.id, user.role.value)

    return {"access_token": token, "token_type": "bearer"}
