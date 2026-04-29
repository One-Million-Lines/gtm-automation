"""Auth module — bcrypt password hashing + JWT tokens + FastAPI dependencies.

Usage:
  - hash_password / verify_password — for user storage
  - create_access_token / decode_token — for session tokens
  - get_current_user — FastAPI Dependency that resolves the bearer token
  - require_project_access(project_id) — enforce project membership
  - require_admin — restrict to admin role
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status

from api_shared import JWT_SECRET, JWT_EXPIRES_HOURS, repos, vtlog

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(*, user_id: int, email: str, role: str = "user",
                        expires_hours: Optional[int] = None) -> str:
    now = _dt.datetime.utcnow()
    exp = now + _dt.timedelta(hours=expires_hours or JWT_EXPIRES_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

def get_current_user(authorization: str = Header(default="")) -> dict:
    """Extract user from `Authorization: Bearer <token>` header.

    Returns the user dict from DB. Raises 401 on any auth failure.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    payload = decode_token(token)
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token subject")
    user = repos.users.get(user_id) if user_id else None
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")
    return user


def get_current_user_optional(authorization: str = Header(default="")) -> Optional[dict]:
    """Same as get_current_user but returns None on failure (for public endpoints)."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required")
    return user


def user_has_project_access(user: dict, project_id: int,
                            required_role: str = "viewer") -> bool:
    """Admin always passes. Otherwise, must have a membership with sufficient role."""
    if user.get("role") == "admin":
        return True
    membership = repos.project_members.get_membership(int(project_id), int(user["id"]))
    if not membership:
        return False
    role_rank = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
    return role_rank.get(membership["role"], -1) >= role_rank.get(required_role, 0)


def require_project_access(project_id: int, *, required_role: str = "viewer"):
    """Use as: Depends(require_project_access(project_id, required_role='member'))"""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if not user_has_project_access(user, project_id, required_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Access denied to project {project_id}")
        return user
    return _dep


def public_user_dict(user: dict) -> dict:
    """Strip sensitive fields before returning over the API."""
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name"),
        "role": user.get("role", "user"),
        "is_active": bool(user.get("is_active", 1)),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }
