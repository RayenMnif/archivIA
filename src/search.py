"""Search indexed scenes with CLIP and optional transcript keyword matching."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import read_index
from ranking import rank_scenes
from ui import enable_ansi, search_header, search_note, search_result, status


def main() -> None:
    enable_ansi()
    parser = argparse.ArgumentParser(description="Rechercher des scènes dans un index local.")
    parser.add_argument("query", help="Recherche en français ou dans une autre langue")
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-anim", action="store_true", help="Désactiver les animations du terminal")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k doit être supérieur ou égal à 1")

    index = read_index(args.index)
    if not any(video.get("scenes") for video in index["videos"]):
        parser.error(f"Aucune scène dans l'index : {args.index}")

    search_header(args.query)
    status("Analyse des vidéos en cours…", animated=not args.no_anim)
    ranked = rank_scenes(index, args.query)
    for number, item in enumerate(ranked[: args.top_k], start=1):
        search_result(number, item["score"], item["visual_similarity"], item["scene"], animated=not args.no_anim)
    search_note()


if __name__ == "__main__":
    main()
