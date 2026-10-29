"""Shared FastAPI dependencies: current user resolution and role gates."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db, security

_bearer = HTTPBearer(auto_error=False)


def _row_to_user(row: sqlite3.Row, connection: sqlite3.Connection) -> dict[str, Any]:
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM fields WHERE owner_id = ? AND deleted_at IS NULL",
        (row["id"],),
    ).fetchone()["n"]
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "phone": row["phone"],
        "role": row["role"],
        "created_at": row["created_at"],
        "field_count": count,
    }


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少登录凭证")
    try:
        payload = security.decode_access_token(credentials.credentials)
    except Exception:  # noqa: BLE001 - any decode failure means "not signed in"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态已失效，请重新登录") from None
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "凭证无效")

    connection = db.get_conn()
    row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return _row_to_user(row, connection)


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


async def admin_user(user: CurrentUser) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


AdminUser = Annotated[dict[str, Any], Depends(admin_user)]
