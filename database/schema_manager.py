from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from database.db_connector import get_db_connection


@lru_cache(maxsize=1)
def ensure_schema() -> None:
    """
    Ensures required tables/columns exist.

    This is intentionally lightweight and idempotent so it can be called
    from entrypoints before writing/reading.
    """
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(schema_sql)

            # Backward-compatible migration for older schema.sql versions.
            cur.execute(
                "ALTER TABLE IF EXISTS ai_events "
                "ADD COLUMN IF NOT EXISTS explanation JSONB"
            )
    finally:
        conn.close()

