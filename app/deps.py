"""
FastAPI dependency functions for authentication and authorization.

These are reusable functions that routes can depend on. FastAPI calls
them automatically and injects the results. This keeps route handlers
clean and authorization logic centralized.
"""

from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token
from jose import JWTError

# HTTPBearer extracts the "Authorization: Bearer <token>" header for us.
oauth2_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency that extracts and validates the JWT from the Authorization header,
    then loads the corresponding User from the database.

    Raises 401 Unauthorized if:
      - no token is present
      - the token is invalid or expired
      - the user doesn't exist
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id_int).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*allowed_roles: str) -> Callable:
    """
    Returns a dependency that checks if the current user's role is in allowed_roles.

    Usage in a route:
        @app.get("/admin")
        def admin_only(current_user: User = Depends(require_role("admin"))):
            ...

    Raises 403 Forbidden if the user's role is not allowed.
    """

    def check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of roles: {allowed_roles}",
            )
        return current_user

    return check_role
