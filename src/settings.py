"""Small atomic persistence for the selected archive folder."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path("data/settings.json")

def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    if not path.exists(): return {"schema_version": 1, "library_root": None, "recent": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("recent"), list): raise ValueError("schéma invalide")
        return {"schema_version": 1, "library_root": data.get("library_root"), "recent": data["recent"][:5]}
    except Exception:
        logging.exception("Fichier de réglages illisible : %s", path)
        return {"schema_version": 1, "library_root": None, "recent": []}

def save_settings(data: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)

def select_library(data: dict[str, Any], root: Path, path: Path = SETTINGS_PATH) -> dict[str, Any]:
    value = str(root.resolve())
    recent = [value, *[item for item in data.get("recent", []) if item != value]][:5]
    result = {"schema_version": 1, "library_root": value, "recent": recent}
    save_settings(result, path)
    return result
