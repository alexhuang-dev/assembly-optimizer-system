from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "assembly_optimizer_v1"

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_HISTORY_DB_PATH = DATA_DIR / "history.db"
DEFAULT_OUTPUT_DIR = DATA_DIR / "reports"

FIT_LIBRARY = {
    "H7/k6": {"interference_um": (-6.0, 18.0), "family": "transition_fit"},
    "H7/m6": {"interference_um": (8.0, 31.0), "family": "light_press_fit"},
    "H7/p6": {"interference_um": (24.0, 60.0), "family": "press_fit"},
    "H7/s6": {"interference_um": (43.0, 82.0), "family": "heavy_press_fit"},
    "H7/u6": {"interference_um": (65.0, 110.0), "family": "shrink_fit"},
}


def resolve_runtime_config(overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    history_db_path = Path(overrides.get("history_db_path") or DEFAULT_HISTORY_DB_PATH)
    output_dir = Path(overrides.get("output_dir") or DEFAULT_OUTPUT_DIR)
    history_db_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "history_db_path": history_db_path,
        "output_dir": output_dir,
    }

