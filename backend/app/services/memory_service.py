"""
Memory service for persistent project-scoped key-value storage.

Stores memory entries in storage/memory/{project_id}.json with optional TTL.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

STORAGE_DIR = Path(__file__).resolve().parents[4] / "storage" / "memory"


def _load(project_id: str) -> dict:
    path = STORAGE_DIR / f"{project_id}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(project_id: str, data: dict) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = STORAGE_DIR / f"{project_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _is_expired(entry: dict) -> bool:
    expires_at = entry.get("expires_at")
    if expires_at is None:
        return False
    return datetime.utcnow() > datetime.fromisoformat(expires_at)


def store_memory(project_id: str, key: str, value: str, ttl_days: int = 30) -> None:
    """Store a key-value memory entry for a project with an optional TTL."""
    data = _load(project_id)
    expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat() if ttl_days else None
    data[key] = {
        "value": value,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at,
    }
    _save(project_id, data)


def recall_memory(project_id: str, key: str) -> Optional[str]:
    """Retrieve a memory value by key, returning None if missing or expired."""
    data = _load(project_id)
    entry = data.get(key)
    if entry is None:
        return None
    if _is_expired(entry):
        return None
    return entry["value"]


def search_memories(project_id: str, query: str) -> list[dict]:
    """Return all non-expired memory entries whose key or value contains the query substring."""
    data = _load(project_id)
    query_lower = query.lower()
    results = []
    for key, entry in data.items():
        if _is_expired(entry):
            continue
        value = entry["value"]
        if query_lower in key.lower() or query_lower in value.lower():
            results.append({
                "key": key,
                "value": value,
                "created_at": entry.get("created_at"),
                "expires_at": entry.get("expires_at"),
            })
    return results
