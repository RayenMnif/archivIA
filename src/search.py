"""Search indexed scenes with CLIP and optional transcript keyword matching."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import torch

from common import load_clip_model, read_index, text_embedding
from ui import enable_ansi, search_header, search_note, search_result, status


def terms(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


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
    scenes = [scene for video in index["videos"] for scene in video.get("scenes", [])]
    if not scenes:
        parser.error(f"Aucune scène dans l'index : {args.index}")

    search_header(args.query)
    status("Analyse des vidéos en cours…", animated=not args.no_anim)
    model, _, tokenizer, device = load_clip_model()
    query_vector = torch.tensor(text_embedding(args.query, model, tokenizer, device))
    query_terms = terms(args.query)
    ranked = []
    for scene in scenes:
        vector = torch.tensor(scene["embedding"])
        similarity = float(torch.dot(query_vector, vector).item())
        transcript_terms = terms(scene.get("transcript", ""))
        overlap = len(query_terms & transcript_terms) / max(1, len(query_terms))
        # A simple tie-break signal, not a calibrated relevance probability.
        score = similarity + 0.05 * overlap
        ranked.append((score, similarity, scene))

    ranked.sort(key=lambda item: item[0], reverse=True)
    for number, (score, similarity, scene) in enumerate(ranked[: args.top_k], start=1):
        search_result(number, score, similarity, scene, animated=not args.no_anim)
    search_note()


if __name__ == "__main__":
    main()
