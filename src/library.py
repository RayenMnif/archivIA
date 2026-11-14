"""Archive scanning, index reconciliation and one-video-at-a-time ingestion."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg"}

def scan_videos(root: Path) -> list[Path]:
    found=[]
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(current)/d).is_symlink()]
        for name in files:
            path=Path(current)/name
            if name.startswith(".") or path.suffix.lower() not in VIDEO_EXTENSIONS or path.is_symlink(): continue
            if name.lower().endswith((".part", ".crdownload", ".tmp")): continue
            if path.is_file(): found.append(path.resolve())
    return sorted(found)

def validate_library(root: str | Path) -> tuple[Path, list[Path]]:
    path=Path(root).expanduser()
    if not path.exists() or not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
        raise ValueError("Ce dossier n'existe pas ou n'est pas accessible en lecture.")
    return path.resolve(), scan_videos(path)

def reconcile(root: Path, index: dict[str, Any]) -> tuple[list[tuple[Path,str]], list[dict]]:
    disk=scan_videos(root)
    indexed={str(Path(v["path"]).resolve()):v for v in index.get("videos",[]) if v.get("path")}
    found={str(p):p for p in disk}; queue=[]
    for key,path in found.items():
        stat=path.stat(); previous=indexed.get(key)
        if previous is None: queue.append((path,"nouveau"))
        elif previous.get("size") != stat.st_size or previous.get("mtime") != stat.st_mtime: queue.append((path,"modifié"))
    missing=[]
    for key,video in indexed.items():
        if key not in found:
            if not video.get("missing"):
                video["missing"]=True
            missing.append(video)
    return queue, missing
