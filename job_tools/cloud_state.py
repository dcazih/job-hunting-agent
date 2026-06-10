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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                  job_id TEXT PRIMARY KEY,
                  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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


def get_seen_job_ids() -> set[str]:
    if not enabled():
        return set()
    ensure_schema()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT job_id FROM seen_jobs")
            return {str(row[0]) for row in cur.fetchall() if row and row[0]}


def add_seen_job_ids(job_ids: Any) -> None:
    if not enabled():
        return
    normalized = sorted(
        {str(job_id).strip() for job_id in (job_ids or []) if str(job_id).strip()}
    )
    if not normalized:
        return
    ensure_schema()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO seen_jobs (job_id)
                VALUES (%s)
                ON CONFLICT (job_id) DO NOTHING;
                """,
                [(job_id,) for job_id in normalized],
            )
        conn.commit()


def remove_seen_job_ids(job_ids: Any) -> None:
    if not enabled():
        return
    normalized = sorted(
        {str(job_id).strip() for job_id in (job_ids or []) if str(job_id).strip()}
    )
    if not normalized:
        return
    ensure_schema()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM seen_jobs WHERE job_id = ANY(%s)", (normalized,))
        conn.commit()
