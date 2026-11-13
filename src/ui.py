"""Terminal presentation helpers for the ArchivIA command-line tools."""

from __future__ import annotations

import os
import sys
import time
from typing import Any


RESET = "\x1b[0m"
COLORS = {
    "green": "\x1b[38;2;78;220;125m",
    "yellow": "\x1b[38;2;245;205;75m",
    "purple": "\x1b[38;2;205;112;220m",
    "blue": "\x1b[38;2;105;155;255m",
    "cyan": "\x1b[38;2;80;205;220m",
    "white": "\x1b[38;2;230;230;238m",
    "muted": "\x1b[38;2;145;145;162m",
}


def enable_ansi() -> None:
    """Enable ANSI sequences in Windows console sessions when possible."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if hasattr(stream, "reconfigure") and encoding != "utf8":
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass
    if os.name != "nt" or not sys.stdout.isatty():
        return
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004 | 0x0008)
    except (AttributeError, OSError):
        pass


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{COLORS[color]}{text}{RESET}" if enabled else text


def status(message: str, *, animated: bool = True, color: str = "purple") -> None:
    enable_ansi()
    prefix = "› "
    if animated and sys.stdout.isatty():
        sys.stdout.write(_paint(prefix, color, True))
        for char in message:
            sys.stdout.write(_paint(char, color, True))
            sys.stdout.flush()
            time.sleep(0.018)
        sys.stdout.write("\n")
    else:
        print(_paint(prefix + message, color, sys.stdout.isatty()))


def message(text: str, kind: str = "info") -> None:
    colors = {"success": "green", "warning": "yellow", "error": "yellow", "info": "muted"}
    enable_ansi()
    print(_paint(text, colors.get(kind, "muted"), sys.stdout.isatty()))


def _bar(score: float, color: str, enabled: bool) -> str:
    filled = max(0, min(20, round(max(0.0, score) * 10)))
    blocks = "█" * filled + "╌" * (20 - filled)
    return _paint(blocks[:filled], color, enabled) + _paint(blocks[filled:], "muted", enabled)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def search_header(query: str) -> None:
    enable_ansi()
    print(_paint("╭─ Recherche " + "─" * 8, "purple", sys.stdout.isatty()))
    print(_paint("│ » " + query, "white", sys.stdout.isatty()))
    print(_paint("╰" + "─" * 30 + "╯", "purple", sys.stdout.isatty()))


def search_result(number: int, score: float, similarity: float, scene: dict[str, Any], *, animated: bool = True) -> None:
    enable_ansi()
    enabled = sys.stdout.isatty()
    accent = "green" if number == 1 else "yellow"
    transcript = scene.get("transcript") or "[aucune parole transcrite]"
    source = scene.get("video_path", "") or scene.get("scene_id", "")
    start, end = scene.get("start", ""), scene.get("end", "")
    duration = f"◷ {start}–{end}"
    title = f"#{number}"
    lines = [
        _paint(f"╭─ {title} " + "─" * 72, "blue", enabled),
        f"│ {_paint(duration, 'cyan', enabled)}   ▶ {source}",
        f"│ {_paint('Similarité visuelle', 'muted', enabled)}  {_bar(similarity, accent, enabled)}  {_paint(f'{similarity:.3f}', accent, enabled)}",
        f"│ {_paint('Score combiné', 'muted', enabled)}      {_bar(score, accent, enabled)}  {_paint(f'{score:.3f}', accent, enabled)}",
    ]
    for line in _wrap(f"« {transcript} »", 92):
        lines.append(f"│ {_paint(line, 'muted', enabled)}")
    lines.append(
        _paint("╰" + "─" * 72, "blue", enabled)
        + "  "
        + _paint(scene.get("status", "proposé"), "yellow", enabled)
    )
    print("\n".join(lines))
    if animated and enabled:
        time.sleep(0.7)


def search_note() -> None:
    message("Les scores sont indicatifs et ne sont pas des probabilités de justesse.")
    message("Chaque résultat est proposé, jamais imposé : la décision reste humaine.")
