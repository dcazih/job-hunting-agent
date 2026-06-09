from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any

import psycopg


DATABASE_URL = (
    os.getenv("DATABASE_URL", "").strip()
    or os.getenv("POSTGRES_URL", "").strip()
)


@contextmanager
def _conn():
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def enabled() -> bool:
    return bool(DATABASE_URL)


def ensure_schema() -> None:
    if not enabled():
        return
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_kv (
                  key TEXT PRIMARY KEY,
                  value JSONB NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()


def get_json(key: str, default: Any = None) -> Any:
    if not enabled():
        return default
    ensure_schema()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_kv WHERE key = %s", (key,))
            row = cur.fetchone()
            if not row:
                return default
            return row[0]


def set_json(key: str, value: Any) -> None:
    if not enabled():
        return
    ensure_schema()
    payload = json.dumps(value)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_kv (key, value, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
                """,
                (key, payload),
            )
        conn.commit()
