"""Shared helpers for the ArchivIA command-line prototype."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import open_clip
import torch
from PIL import Image

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"


def load_clip_model():
    """Load the visual-language model and its transforms on the available device."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        MODEL_NAME, pretrained=PRETRAINED, device=device
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(MODEL_NAME)
    return model, preprocess, tokenizer, device


def image_embedding(image_path: Path, model: Any, preprocess: Any, device: str) -> list[float]:
    image = Image.open(image_path).convert("RGB")
    tensor = preprocess(image).unsqueeze(0).to(device)
    with torch.inference_mode():
        vector = model.encode_image(tensor)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector[0].cpu().tolist()


def text_embedding(query: str, model: Any, tokenizer: Any, device: str) -> list[float]:
    tokens = tokenizer([query]).to(device)
    with torch.inference_mode():
        vector = model.encode_text(tokens)
        vector = vector / vector.norm(dim=-1, keepdim=True)
    return vector[0].cpu().tolist()


def read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "videos": []}
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if data.get("schema_version") != 1 or not isinstance(data.get("videos"), list):
        raise ValueError(f"Format d'index non reconnu : {path}")
    return data


def write_index(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)
