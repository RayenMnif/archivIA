"""Index a video without modifying the original file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import hashlib

import cv2
import torch
import whisper
from scenedetect import ContentDetector, SceneManager, open_video

from common import image_embedding, load_clip_model, read_index, write_index
from ui import enable_ansi, message, status


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


def configure_ffmpeg(explicit_path: Path | None) -> str:
    """Make ffmpeg available to Whisper, including portable Winget installs."""
    candidates: list[Path] = []
    if explicit_path is not None:
        candidate = explicit_path.expanduser()
        if candidate.is_dir():
            candidate /= "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        candidates.append(candidate)

    found_on_path = shutil.which("ffmpeg")
    if found_on_path:
        return found_on_path

    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
        winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates.extend(
            winget_packages.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe")
        )

    for candidate in candidates:
        if candidate.is_file():
            os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
            return str(candidate)

    raise RuntimeError(
        "ffmpeg est introuvable. Installez-le et ajoutez son dossier bin au PATH, "
        "ou indiquez ce dossier avec --ffmpeg-bin."
    )


def ingest_video(video_path: Path, rights: dict, *, frames_dir: Path = Path("data/frames"),
                 whisper_model: str = "base", language: str | None = None,
                 ffmpeg_bin: Path | None = None, library_root: Path | None = None,
                 progress=None) -> list[dict]:
    """Index one video and return its scene records; source media is untouched."""
    video_path = video_path.expanduser().resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"Vidéo introuvable : {video_path}")
    configure_ffmpeg(ffmpeg_bin)
    if progress: progress("Détection des scènes")
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
    if progress: progress("Transcription")
    whisper_device = "cuda" if torch.cuda.is_available() else "cpu"
    transcriber = whisper.load_model(whisper_model, device=whisper_device)
    transcription = transcriber.transcribe(
        str(video_path), language=language, fp16=whisper_device == "cuda", verbose=False
    )
    transcript_segments = transcription.get("segments", [])
    if progress: progress("Images clés")
    relative = video_path.relative_to(library_root.resolve()) if library_root else Path(video_path.name)
    safe = "_".join(relative.with_suffix("").parts)
    suffix = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:10]
    frame_dir = frames_dir / f"{safe}_{suffix}"
    if progress: progress("Représentations visuelles")
    model, preprocess, _, device = load_clip_model()
    records = []
    for number, (start, end) in enumerate(scenes, start=1):
        start_seconds, end_seconds = start.get_seconds(), end.get_seconds()
        frame_path = frame_dir / f"scene_{number:04d}.jpg"
        extract_frame(video_path, (start_seconds + end_seconds) / 2, frame_path)
        transcript = " ".join(segment.get("text", "").strip() for segment in transcript_segments
            if segment.get("start", 0) < end_seconds and segment.get("end", 0) > start_seconds).strip()
        thumb = frame_path.with_name(frame_path.stem + "_thumb.jpg")
        image = cv2.imread(str(frame_path))
        if image is not None:
            height, width = image.shape[:2]
            scale = 320 / max(width, height)
            cv2.imwrite(str(thumb), cv2.resize(image, (max(1, int(width*scale)), max(1, int(height*scale)))))
        records.append({"scene_id": f"{suffix}:{number:04d}", "video_path": str(video_path),
            "start_seconds": round(start_seconds, 3), "end_seconds": round(end_seconds, 3),
            "start": format_time(start_seconds), "end": format_time(end_seconds),
            "keyframe": str(frame_path.resolve()), "thumbnail": str(thumb.resolve()),
            "embedding": image_embedding(frame_path, model, preprocess, device), "transcript": transcript,
            "status": "proposé", "generated_by_ai": True})
    return records


def main() -> None:
    enable_ansi()
    parser = argparse.ArgumentParser(description="Indexer une vidéo d'archive en local.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--rights-holder", required=True, help="Titulaire des droits, ou mention explicite de l'incertitude")
    parser.add_argument("--license", required=True, help="Licence ou statut de droits vérifié")
    parser.add_argument("--allowed-uses", required=True, help="Usages autorisés pour cette démonstration")
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--frames-dir", type=Path, default=Path("data/frames"))
    parser.add_argument("--ffmpeg-bin", type=Path, default=None, help="Dossier contenant ffmpeg.exe (facultatif)")
    parser.add_argument("--whisper-model", choices=("tiny", "base", "small"), default="base")
    parser.add_argument("--language", default=None, help="Code langue Whisper facultatif, par ex. fr ou ar")
    parser.add_argument("--no-anim", action="store_true", help="Désactiver les animations du terminal")
    args = parser.parse_args()

    video_path = args.video.expanduser().resolve()
    if not video_path.is_file():
        parser.error(f"Vidéo introuvable : {video_path}")

    try:
        ffmpeg_path = configure_ffmpeg(args.ffmpeg_bin)
    except RuntimeError as error:
        parser.error(str(error))
    message(f"FFmpeg : {ffmpeg_path}")
    def report(stage: str) -> None:
        if stage == "Détection des scènes":
            status("Détection des scènes…", animated=not args.no_anim)
        elif stage == "Transcription":
            status(f"Transcription Whisper ({args.whisper_model})…", animated=not args.no_anim)
        elif stage == "Représentations visuelles":
            status("Calcul des représentations visuelles CLIP…", animated=not args.no_anim)
    records = ingest_video(video_path, {"holder": args.rights_holder, "license": args.license,
        "allowed_uses": args.allowed_uses}, frames_dir=args.frames_dir, whisper_model=args.whisper_model,
        language=args.language, ffmpeg_bin=args.ffmpeg_bin, progress=report)

    index = read_index(args.index)
    index["videos"] = [item for item in index["videos"] if item.get("path") != str(video_path)]
    index["videos"].append(
        {
            "path": str(video_path),
            "rights": {"holder": args.rights_holder, "license": args.license, "allowed_uses": args.allowed_uses},
            "models": {
                "transcription": f"openai/whisper-{args.whisper_model}",
                "visual_embedding": f"open_clip/{'ViT-B-32'}:{'laion2b_s34b_b79k'}",
            },
            "scenes": records,
        }
    )
    write_index(args.index, index)
    message(f"{len(records)} scènes indexées dans {args.index}. La vidéo source n'a pas été modifiée.", "success")


if __name__ == "__main__":
    main()
