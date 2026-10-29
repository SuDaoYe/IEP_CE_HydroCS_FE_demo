"""SQLite persistence layer.

Deliberately dependency-free (stdlib ``sqlite3``) so the demo runs on a plain
Python install. Geometry is stored as GeoJSON text plus a bbox for cheap
filtering; authoritative area is computed in Python.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,
    phone       TEXT,
    name        TEXT NOT NULL,
    pass_hash   TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'farmer',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fields (
    id            TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL REFERENCES users(id),
    name          TEXT NOT NULL,
    crop          TEXT,
    stage_key     TEXT,
    plant_date    TEXT,
    geom_json     TEXT NOT NULL,
    bbox_minx     REAL NOT NULL,
    bbox_miny     REAL NOT NULL,
    bbox_maxx     REAL NOT NULL,
    bbox_maxy     REAL NOT NULL,
    area_m2       REAL NOT NULL,
    source        TEXT NOT NULL DEFAULT 'manual',
    confidence    REAL,
    note          TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    deleted_at    TEXT,
    rev           INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_fields_owner ON fields(owner_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_fields_bbox ON fields(bbox_minx, bbox_miny, bbox_maxx, bbox_maxy);

CREATE TABLE IF NOT EXISTS irrigation_logs (
    id           TEXT PRIMARY KEY,
    field_id     TEXT NOT NULL REFERENCES fields(id),
    user_id      TEXT NOT NULL,
    computed_at  TEXT NOT NULL,
    days         INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_field ON irrigation_logs(field_id, computed_at DESC);

CREATE TABLE IF NOT EXISTS sync_ops (
    op_id      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    entity_id  TEXT,
    payload    TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS params (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 区域化的模型系数：彭曼公式的标定系数随气候区不同，按行政区层级覆盖
CREATE TABLE IF NOT EXISTS param_scopes (
    scope      TEXT NOT NULL,           -- 'global' | 'province:370000' | 'city:370500'
    param      TEXT NOT NULL,
    value      REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT,
    PRIMARY KEY (scope, param)
);
"""

_local = threading.local()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:16]
    return f"{prefix}{raw}" if prefix else raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_conn() -> sqlite3.Connection:
    """Thread-local connection; FastAPI sync endpoints run in a thread pool."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# --- parameters -----------------------------------------------------------


def get_param(key: str, default: Any = None) -> Any:
    row = get_conn().execute("SELECT value_json FROM params WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else default


def set_param(key: str, value: Any) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT INTO params(key, value_json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), now_iso()),
        )
