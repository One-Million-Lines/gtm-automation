"""Auth API — register, login, me, change-password.

Routes are intentionally public (no auth required) except /me and /change-password.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api_shared import repos, vtlog
from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    public_user_dict,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ALLOW_REGISTRATION = (os.environ.get("ALLOW_REGISTRATION", "true").lower()
                      in ("1", "true", "yes"))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn) -> TokenOut:
    if not ALLOW_REGISTRATION:
        # Allow only the very first user, then disable
        any_user = repos.users.find_one({})
        if any_user is not None:
            raise HTTPException(status_code=403, detail="Registration disabled")

    email = payload.email.strip().lower()
    if repos.users.get_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    # First user becomes admin
    is_first = repos.users.find_one({}) is None
    role = "admin" if is_first else "user"

    user_id = repos.users.create({
        "email": email,
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": role,
        "is_active": 1,
    })
    user = repos.users.get(user_id)
    repos.users.touch_login(user_id)
    vtlog.info("auth_register", user_id=user_id, email=email, role=role)

    token = create_access_token(user_id=user_id, email=email, role=role)
    return TokenOut(access_token=token, user=public_user_dict(user))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn) -> TokenOut:
    email = payload.email.strip().lower()
    user = repos.users.get_by_email(email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        vtlog.warning("auth_login_failed", email=email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User disabled")

    repos.users.touch_login(user["id"])
    token = create_access_token(user_id=user["id"], email=email,
                                role=user.get("role", "user"))
    vtlog.info("auth_login", user_id=user["id"], email=email)
    return TokenOut(access_token=token, user=public_user_dict(user))


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    memberships = repos.project_members.list_for_user(user["id"])
    return {"user": public_user_dict(user), "memberships": memberships}


@router.post("/change-password")
def change_password(payload: ChangePasswordIn,
                    user: dict = Depends(get_current_user)) -> dict:
    if not verify_password(payload.old_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Old password incorrect")
    repos.users.update(user["id"], {"password_hash": hash_password(payload.new_password)})
    return {"ok": True}
