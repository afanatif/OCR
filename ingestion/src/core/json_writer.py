"""
JSON I/O helpers — thin wrappers that handle path creation and logging.
"""

import json
from pathlib import Path
from typing import Any

from src.core.logger import logger


def write_json(data: Any, path: Path, indent: int = 2) -> None:
    """Write `data` as pretty-printed JSON to `path`, creating dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    logger.success(f"Written -> {path}")


def read_json(path: Path) -> Any:
    """Read and return JSON from `path`."""
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.debug(f"Loaded <- {path}")
    return data
