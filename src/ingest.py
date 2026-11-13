"""Index a video without modifying the original file."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import whisper
from scenedetect import ContentDetector, SceneManager, open_video

from common import image_embedding, load_clip_model, read_index, write_index


def format_time(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}"


def extract_frame(video_path: Path, seconds: float, destination: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"Image impossible à extraire à {seconds:.2f} s")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), frame):
            raise RuntimeError(f"Écriture impossible : {destination}")
    finally:
        capture.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexer une vidéo d'archive en local.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--rights-holder", required=True, help="Titulaire des droits, ou mention explicite de l'incertitude")
    parser.add_argument("--license", required=True, help="Licence ou statut de droits vérifié")
    parser.add_argument("--allowed-uses", required=True, help="Usages autorisés pour cette démonstration")
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--frames-dir", type=Path, default=Path("data/frames"))
    parser.add_argument("--whisper-model", choices=("tiny", "base", "small"), default="base")
    parser.add_argument("--language", default=None, help="Code langue Whisper facultatif, par ex. fr ou ar")
    args = parser.parse_args()

    video_path = args.video.expanduser().resolve()
    if not video_path.is_file():
        parser.error(f"Vidéo introuvable : {video_path}")

    print("Détection des scènes…")
    video = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    manager.detect_scenes(video=video)
    scenes = manager.get_scene_list()
    if not scenes:
        duration = video.duration.get_seconds()
        if duration <= 0:
            raise RuntimeError("La durée de la vidéo n'a pas pu être déterminée.")
        scenes = [(video.base_timecode, video.base_timecode + video.duration)]

    print(f"Transcription Whisper ({args.whisper_model})…")
    transcriber = whisper.load_model(args.whisper_model, device="cpu")
    transcription = transcriber.transcribe(
        str(video_path), language=args.language, fp16=False, verbose=False
    )
    transcript_segments = transcription.get("segments", [])

    print("Calcul des représentations visuelles CLIP…")
    model, preprocess, _, device = load_clip_model()
    frame_dir = args.frames_dir / video_path.stem
    records = []
    for number, (start, end) in enumerate(scenes, start=1):
        start_seconds = start.get_seconds()
        end_seconds = end.get_seconds()
        midpoint = (start_seconds + end_seconds) / 2
        frame_path = frame_dir / f"scene_{number:04d}.jpg"
        extract_frame(video_path, midpoint, frame_path)
        transcript = " ".join(
            segment.get("text", "").strip()
            for segment in transcript_segments
            if segment.get("start", 0) < end_seconds and segment.get("end", 0) > start_seconds
        ).strip()
        records.append(
            {
                "scene_id": f"{video_path.stem}:{number:04d}",
                "video_path": str(video_path),
                "start_seconds": round(start_seconds, 3),
                "end_seconds": round(end_seconds, 3),
                "start": format_time(start_seconds),
                "end": format_time(end_seconds),
                "keyframe": str(frame_path.resolve()),
                "embedding": image_embedding(frame_path, model, preprocess, device),
                "transcript": transcript,
                "status": "proposé",
                "generated_by_ai": True,
            }
        )

    index = read_index(args.index)
    index["videos"] = [item for item in index["videos"] if item.get("path") != str(video_path)]
    index["videos"].append(
        {
            "path": str(video_path),
            "rights": {
                "holder": args.rights_holder,
                "license": args.license,
                "allowed_uses": args.allowed_uses,
            },
            "models": {
                "transcription": f"openai/whisper-{args.whisper_model}",
                "visual_embedding": f"open_clip/{'ViT-B-32'}:{'laion2b_s34b_b79k'}",
            },
            "scenes": records,
        }
    )
    write_index(args.index, index)
    print(f"{len(records)} scènes indexées dans {args.index}. La vidéo source n'a pas été modifiée.")


if __name__ == "__main__":
    main()
