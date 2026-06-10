from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from job_tools.cloud_state import enabled as cloud_enabled
from job_tools.cloud_state import get_json as cloud_get_json
from job_tools.cloud_state import set_json as cloud_set_json


CHECKPOINT_KEY = "search.latest_checkpoint"
CHECKPOINT_PATH = Path("data/latest_search_checkpoint.json")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_search_checkpoint() -> dict[str, Any] | None:
    if cloud_enabled():
        payload = cloud_get_json(CHECKPOINT_KEY, None)
        return dict(payload) if isinstance(payload, dict) else None

    if not CHECKPOINT_PATH.exists():
        return None
    try:
        payload = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return dict(payload) if isinstance(payload, dict) else None


def save_search_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    checkpoint = dict(payload)
    checkpoint["updated_at"] = _now_iso()
    if cloud_enabled():
        cloud_set_json(CHECKPOINT_KEY, checkpoint)
    else:
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_PATH.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    return checkpoint


def start_search_checkpoint(run_id: str, params: dict[str, Any]) -> dict[str, Any]:
    return save_search_checkpoint(
        {
            "version": 1,
            "run_id": str(run_id or ""),
            "status": "active",
            "phase": "fetching",
            "params": dict(params),
            "fetched_jobs": [],
            "filter_decisions": {},
            "filtered_jobs": [],
            "scored_jobs": [],
            "created_at": _now_iso(),
        }
    )


def update_search_checkpoint(**changes: Any) -> dict[str, Any] | None:
    checkpoint = load_search_checkpoint()
    if checkpoint is None:
        return None
    checkpoint.update(changes)
    return save_search_checkpoint(checkpoint)


def mark_search_checkpoint_interrupted(run_id: str = "") -> dict[str, Any] | None:
    checkpoint = load_search_checkpoint()
    if checkpoint is None:
        return None
    expected_run_id = str(run_id or "").strip()
    if expected_run_id and str(checkpoint.get("run_id", "") or "") != expected_run_id:
        return checkpoint
    if checkpoint.get("status") != "active":
        return checkpoint
    checkpoint["status"] = "interrupted"
    return save_search_checkpoint(checkpoint)


def mark_search_checkpoint_complete() -> dict[str, Any] | None:
    return update_search_checkpoint(status="complete", phase="complete")
