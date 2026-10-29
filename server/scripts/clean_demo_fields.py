"""Remove leftover test parcels (and their irrigation logs) from the demo DB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db

PATTERNS = ("新田块%", "冒烟测试%", "同步田%")

db.init_db()
with db.transaction() as conn:
    targets = [
        row["id"]
        for pattern in PATTERNS
        for row in conn.execute("SELECT id FROM fields WHERE name LIKE ?", (pattern,)).fetchall()
    ]
    for field_id in targets:
        conn.execute("DELETE FROM irrigation_logs WHERE field_id = ?", (field_id,))
        conn.execute("DELETE FROM fields WHERE id = ?", (field_id,))

print("removed fields:", len(targets))
rows = db.get_conn().execute(
    "SELECT name, crop FROM fields WHERE deleted_at IS NULL ORDER BY name"
).fetchall()
for row in rows:
    print("  live:", row["name"], row["crop"])
