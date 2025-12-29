import argparse
import json
import logging
import os
from pathlib import Path

import imageio_ffmpeg


def setup_ffmpeg() -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = str(Path(ffmpeg_exe).parent)
    os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def load_diarization(audio_path: str, num_speakers: int) -> tuple[list[dict], str | None]:
    token = os.environ.get("PYANNOTE_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return [], "pyannote.audio not installed"
    if not token:
        return [], "PYANNOTE_TOKEN not set"
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=token)
    diarization = pipeline(audio_path, num_speakers=num_speakers)
    diar_segments: list[dict] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        diar_segments.append({"start": float(turn.start), "end": float(turn.end), "speaker": speaker})
    return diar_segments, None


def transcribe_segments(audio_path: str, model_name: str, device: str, compute_type: str) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(audio_path, vad_filter=True)
    results = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            results.append({"start": float(segment.start), "end": float(segment.end), "text": text})
    return results


def assign_speakers(segments: list[dict], diar_segments: list[dict]) -> list[dict]:
    if not diar_segments:
        for index, segment in enumerate(segments):
            segment["speaker"] = "SPEAKER_00" if index % 2 == 0 else "SPEAKER_01"
        return segments
    for segment in segments:
        best_speaker = None
        best_overlap = 0.0
        for diar in diar_segments:
            overlap = min(segment["end"], diar["end"]) - max(segment["start"], diar["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar["speaker"]
        if best_speaker:
            segment["speaker"] = best_speaker
    return segments


def map_to_ramu_riya(segments: list[dict]) -> tuple[list[dict], dict]:
    speaker_map: dict[str, str] = {}
    order = ["Ramu", "Riya"]
    next_index = 0
    for segment in segments:
        raw = segment.get("speaker")
        if not raw:
            continue
        key = str(raw).lower()
        if key in ("ramu",):
            speaker_map[key] = "Ramu"
        elif key in ("riya", "raju"):
            speaker_map[key] = "Riya"
        if key not in speaker_map:
            if next_index >= len(order):
                continue
            speaker_map[key] = order[next_index]
            next_index += 1
        segment["speaker_mapped"] = speaker_map[key]
    return segments, speaker_map


def merge_segments(segments: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for segment in segments:
        speaker = segment.get("speaker_mapped") or "Ramu"
        text = segment["text"]
        if merged and merged[-1]["speaker"] == speaker:
            merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
        else:
            merged.append({"speaker": speaker, "text": text})
    return merged


def build_output(lines: list[dict]) -> str:
    return "\n".join([f"{line['speaker']}: {line['text']}" for line in lines])


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe audio to two-speaker script.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "base"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--num-speakers", type=int, default=2)
    args = parser.parse_args()

    logging.getLogger("pyannote").setLevel(logging.WARNING)
    setup_ffmpeg()

    segments = transcribe_segments(args.audio, args.model, args.device, args.compute_type)
    diar_segments, diar_error = load_diarization(args.audio, args.num_speakers)
    segments = assign_speakers(segments, diar_segments)
    segments, speaker_map = map_to_ramu_riya(segments)
    lines = merge_segments(segments)

    duration_seconds = 0.0
    if segments:
        duration_seconds = max(segment["end"] for segment in segments)

    output_payload = {
        "status": "ok",
        "text": build_output(lines),
        "duration_seconds": round(duration_seconds, 2),
        "speaker_map": speaker_map,
        "diarization": "ok" if diar_segments else "fallback",
        "diarization_error": diar_error,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
