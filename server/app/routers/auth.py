"""Authentication: registration, login and profile."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status

from .. import db, deps, security
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(row: sqlite3.Row, field_count: int | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "phone": row["phone"],
        "role": row["role"],
        "created_at": row["created_at"],
        "field_count": field_count,
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> TokenResponse:
    conn = db.get_conn()
    exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (payload.username,)).fetchone()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已被占用")
    user_id = db.new_id("u_")
    created = db.now_iso()
    with db.transaction() as txn:
        txn.execute(
            "INSERT INTO users(id, username, phone, name, pass_hash, role, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                user_id,
                payload.username,
                payload.phone,
                payload.name,
                security.hash_password(payload.password),
                payload.role,
                created,
            ),
        )
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token = security.create_access_token(user_id, payload.role)
    return TokenResponse(access_token=token, user=UserOut(**_user_payload(row, 0)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? OR phone = ?",
        (payload.username, payload.username),
    ).fetchone()
    if row is None or not security.verify_password(payload.password, row["pass_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM fields WHERE owner_id = ? AND deleted_at IS NULL", (row["id"],)
    ).fetchone()["n"]
    token = security.create_access_token(row["id"], row["role"])
    return TokenResponse(access_token=token, user=UserOut(**_user_payload(row, count)))


@router.get("/me", response_model=UserOut)
def me(user: deps.CurrentUser) -> UserOut:
    return UserOut(**user)
