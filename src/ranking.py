"""Shared scene ranking used by both the CLI and desktop interface."""
from __future__ import annotations

import re
from typing import Any, Callable

import torch

from common import load_clip_model, text_embedding


def terms(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def rank_scenes(index: dict[str, Any], query: str, *, embed_query: Callable[[str], list[float]] | None = None) -> list[dict[str, Any]]:
    """Return ranked scenes with visual, keyword and combined scores."""
    scenes = [scene for video in index.get("videos", []) for scene in video.get("scenes", [])]
    if not scenes:
        return []
    if embed_query is None:
        model, _, tokenizer, device = load_clip_model()
        embed_query = lambda value: text_embedding(value, model, tokenizer, device)
    query_vector = torch.tensor(embed_query(query))
    query_terms = terms(query)
    ranked = []
    for scene in scenes:
        vector = torch.tensor(scene["embedding"])
        similarity = float(torch.dot(query_vector, vector).item())
        transcript_terms = terms(scene.get("transcript", ""))
        overlap = len(query_terms & transcript_terms) / max(1, len(query_terms))
        ranked.append({"scene": scene, "visual_similarity": similarity,
                       "keyword_overlap": overlap, "score": similarity + 0.05 * overlap})
    return sorted(ranked, key=lambda row: row["score"], reverse=True)
