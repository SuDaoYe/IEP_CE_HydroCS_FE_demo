"""Offline-first synchronisation: idempotent batch apply of client operations."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import db, deps, repository
from ..schemas import SyncRequest, SyncResult

router = APIRouter(tags=["sync"])


@router.post("/sync", response_model=SyncResult)
def sync(payload: SyncRequest, user: deps.CurrentUser) -> SyncResult:
    applied: list[str] = []
    skipped: list[str] = []
    conflicts: list[dict[str, Any]] = []
    conn = db.get_conn()

    for op in payload.ops:
        seen = conn.execute("SELECT 1 FROM sync_ops WHERE op_id = ?", (op.op_id,)).fetchone()
        if seen:
            skipped.append(op.op_id)
            continue

        try:
            if op.kind == "field.create":
                data = dict(op.payload)
                if op.entity_id:
                    data["id"] = op.entity_id
                repository.create_field(user["id"], {**data, "created_at": op.client_updated_at})
            elif op.kind == "field.update":
                if not op.entity_id:
                    conflicts.append({"op_id": op.op_id, "reason": "缺少 entity_id"})
                    continue
                repository.update_field(
                    op.entity_id,
                    {**op.payload, "source": op.payload.get("source", "manual")},
                    user["id"],
                )
            elif op.kind == "field.delete":
                if not op.entity_id:
                    conflicts.append({"op_id": op.op_id, "reason": "缺少 entity_id"})
                    continue
                repository.delete_field(op.entity_id, user["id"])
        except repository.FieldError as exc:
            if exc.status_code == 409:
                conflicts.append(
                    {
                        "op_id": op.op_id,
                        "entity_id": op.entity_id,
                        "reason": exc.message,
                        "server": _field_snapshot(op.entity_id),
                    }
                )
            else:
                conflicts.append({"op_id": op.op_id, "entity_id": op.entity_id, "reason": exc.message})
            continue
        except Exception as exc:  # noqa: BLE001 - never lose a client op silently
            conflicts.append({"op_id": op.op_id, "reason": f"{exc.__class__.__name__}: {exc}"})
            continue

        with db.transaction() as txn:
            txn.execute(
                "INSERT INTO sync_ops(op_id, user_id, kind, entity_id, payload, applied_at)"
                " VALUES(?,?,?,?,?,?)",
                (
                    op.op_id,
                    user["id"],
                    op.kind,
                    op.entity_id,
                    json.dumps(op.payload, ensure_ascii=False),
                    db.now_iso(),
                ),
            )
        applied.append(op.op_id)

    return SyncResult(
        applied=applied,
        skipped=skipped,
        conflicts=conflicts,
        server_time=db.now_iso(),
        fields=repository.list_fields(owner_id=user["id"]),
    )


def _field_snapshot(field_id: str | None) -> dict[str, Any] | None:
    if not field_id:
        return None
    row = db.get_conn().execute(
        "SELECT f.*, u.name AS owner_name FROM fields f JOIN users u ON u.id = f.owner_id WHERE f.id = ?",
        (field_id,),
    ).fetchone()
    return repository.serialize(row, row["owner_name"]) if row else None


@router.get("/sync/state")
def state(user: deps.CurrentUser) -> dict[str, Any]:
    conn = db.get_conn()
    last = conn.execute(
        "SELECT applied_at FROM sync_ops WHERE user_id = ? ORDER BY applied_at DESC LIMIT 1",
        (user["id"],),
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM sync_ops WHERE user_id = ?", (user["id"],)
    ).fetchone()["n"]
    fields = repository.list_fields(owner_id=user["id"])
    return {
        "server_time": db.now_iso(),
        "last_applied_at": last["applied_at"] if last else None,
        "applied_ops": count,
        "server_rev": max((f["rev"] for f in fields), default=0),
        "fields": fields,
    }
