from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def ensure_history_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                fit_code TEXT NOT NULL,
                primary_method TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                safety_factor REAL,
                torque_margin REAL,
                press_force_kn REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        columns = _table_columns(connection, "runs")
        if "scenario_key" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN scenario_key TEXT NOT NULL DEFAULT 'legacy'")
        connection.commit()


def save_run(db_path: Path, record: dict) -> None:
    ensure_history_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs
            (run_id, created_at, fit_code, primary_method, risk_level, safety_factor, torque_margin, press_force_kn, payload_json, scenario_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["run_id"],
                record["created_at"],
                record["fit_code"],
                record["primary_method"],
                record["risk_level"],
                record["safety_factor"],
                record["torque_margin"],
                record["press_force_kn"],
                json.dumps(record["payload"], ensure_ascii=False),
                record["scenario_key"],
            ),
        )
        connection.commit()


def count_runs(db_path: Path) -> int:
    ensure_history_db(db_path)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM runs").fetchone()
    return int(row[0]) if row else 0


def fetch_recent_runs(db_path: Path, limit: int = 20) -> list[dict]:
    ensure_history_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT run_id, created_at, fit_code, primary_method, risk_level, safety_factor, torque_margin, press_force_kn, scenario_key
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_previous_run(db_path: Path, scenario_key: str | None = None) -> dict | None:
    ensure_history_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if scenario_key:
            row = connection.execute(
                """
                SELECT run_id, created_at, fit_code, primary_method, risk_level, safety_factor, torque_margin, press_force_kn, scenario_key
                FROM runs
                WHERE scenario_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (scenario_key,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT run_id, created_at, fit_code, primary_method, risk_level, safety_factor, torque_margin, press_force_kn, scenario_key
                FROM runs
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
    return dict(row) if row else None


def compare_with_previous(calc_result: dict, previous_run: dict | None) -> dict:
    if not previous_run:
        return {"has_previous": False}

    current_safety = calc_result["stress"]["hub_safety_factor"] or 0.0
    current_torque_margin = calc_result["margins"]["torque_margin"] or 0.0

    return {
        "has_previous": True,
        "previous_run_id": previous_run["run_id"],
        "previous_fit_code": previous_run["fit_code"],
        "previous_scenario_key": previous_run.get("scenario_key"),
        "safety_factor_delta": round(current_safety - (previous_run["safety_factor"] or 0.0), 3),
        "torque_margin_delta": round(current_torque_margin - (previous_run["torque_margin"] or 0.0), 3),
        "press_force_kn_delta": round(calc_result["capacities"]["press_force_kn"] - previous_run["press_force_kn"], 3),
    }
