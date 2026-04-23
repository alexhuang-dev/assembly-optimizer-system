from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from core.config import DATA_DIR, DEFAULT_HISTORY_DB_PATH, DEFAULT_OUTPUT_DIR
from multiagent.llm import LLMRuntimeConfig, resolve_llm_runtime_config

DEFAULT_MULTIAGENT_CHECKPOINT_DB_PATH = DATA_DIR / "multiagent_checkpoints.db"
DEFAULT_MULTIAGENT_OPERATIONS_DB_PATH = DATA_DIR / "multiagent_operations.db"
DEFAULT_MULTIAGENT_DISPATCH_DIR = DEFAULT_OUTPUT_DIR / "dispatch"


@dataclass(frozen=True)
class MultiAgentRuntimeConfig:
    history_db_path: Path
    output_dir: Path
    checkpoint_db_path: Path
    operations_db_path: Path
    dispatch_dir: Path
    llm: LLMRuntimeConfig


def resolve_multiagent_runtime_config(overrides: dict[str, Any] | None = None) -> MultiAgentRuntimeConfig:
    overrides = overrides or {}

    history_db_path = Path(overrides.get("history_db_path") or DEFAULT_HISTORY_DB_PATH)
    output_dir = Path(overrides.get("output_dir") or DEFAULT_OUTPUT_DIR)
    checkpoint_db_path = Path(overrides.get("checkpoint_db_path") or DEFAULT_MULTIAGENT_CHECKPOINT_DB_PATH)
    operations_db_path = Path(overrides.get("operations_db_path") or DEFAULT_MULTIAGENT_OPERATIONS_DB_PATH)
    dispatch_dir = Path(overrides.get("dispatch_dir") or DEFAULT_MULTIAGENT_DISPATCH_DIR)

    for path in (history_db_path, output_dir, checkpoint_db_path, operations_db_path, dispatch_dir):
        path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return MultiAgentRuntimeConfig(
        history_db_path=history_db_path,
        output_dir=output_dir,
        checkpoint_db_path=checkpoint_db_path,
        operations_db_path=operations_db_path,
        dispatch_dir=dispatch_dir,
        llm=resolve_llm_runtime_config(overrides),
    )


def create_checkpointer(db_path: Path) -> tuple[sqlite3.Connection, SqliteSaver]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    return connection, SqliteSaver(connection)


def ensure_operations_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_journal (
                thread_id TEXT NOT NULL,
                action_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (thread_id, action_key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_events (
                thread_id TEXT NOT NULL,
                event_index INTEGER NOT NULL,
                scenario_key TEXT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (thread_id, event_index)
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(memory_events)").fetchall()
        }
        if "scenario_key" not in columns:
            connection.execute("ALTER TABLE memory_events ADD COLUMN scenario_key TEXT")
        connection.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_thread_id(seed: str) -> str:
    fingerprint = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"assembly-ma-{timestamp}-{fingerprint}"


def build_action_key(execution_plan: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(execution_plan, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def get_execution_record(db_path: Path, thread_id: str, action_key: str) -> dict[str, Any] | None:
    ensure_operations_db(db_path)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT result_json
            FROM execution_journal
            WHERE thread_id = ? AND action_key = ?
            """,
            (thread_id, action_key),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def dispatch_instruction_plan(
    db_path: Path,
    dispatch_dir: Path,
    thread_id: str,
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    ensure_operations_db(db_path)
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    action_key = execution_plan["action_key"]
    existing = get_execution_record(db_path, thread_id, action_key)
    if existing:
        return existing

    dispatch_path = dispatch_dir / f"{thread_id}_{action_key}.json"
    dispatch_payload = {
        "thread_id": thread_id,
        "action_key": action_key,
        "created_at": _utc_now(),
        "execution_plan": execution_plan,
    }
    dispatch_path.write_text(json.dumps(dispatch_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {
        "status": "published",
        "action_key": action_key,
        "dispatch_path": str(dispatch_path),
        "published_at": dispatch_payload["created_at"],
    }

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO execution_journal
            (thread_id, action_key, created_at, payload_json, result_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                action_key,
                dispatch_payload["created_at"],
                json.dumps(dispatch_payload, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        connection.commit()

    return result


def append_memory_events(db_path: Path, thread_id: str, scenario_key: str, events: list[dict[str, Any]]) -> int:
    ensure_operations_db(db_path)
    if not events:
        return 0

    with sqlite3.connect(db_path) as connection:
        existing_count = connection.execute(
            "SELECT COUNT(*) FROM memory_events WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()[0]

        rows = []
        for index, event in enumerate(events, start=existing_count):
            rows.append(
                (
                    thread_id,
                    index,
                    scenario_key,
                    _utc_now(),
                    event.get("type", "unknown"),
                    json.dumps(event, ensure_ascii=False),
                )
            )

        connection.executemany(
            """
            INSERT OR REPLACE INTO memory_events
            (thread_id, event_index, scenario_key, created_at, event_type, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    return len(events)


def fetch_recent_memory_events(db_path: Path, scenario_key: str, limit: int = 8) -> list[dict[str, Any]]:
    ensure_operations_db(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM memory_events
            WHERE scenario_key = ?
            ORDER BY created_at DESC, event_index DESC
            LIMIT ?
            """,
            (scenario_key, limit),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]
