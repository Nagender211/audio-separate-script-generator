import argparse
import asyncio
import json
import random
import re
import subprocess
import wave
from array import array
from pathlib import Path

import edge_tts
import imageio_ffmpeg

SEGMENT_SECONDS = 60
DEFAULT_MINUTES = 60
DEFAULT_RATE = "-5%"
DEFAULT_SEED = 42
DEFAULT_TURNS_PER_MINUTE = 4
DEFAULT_WORDS_PER_SECOND = 2.0
DEFAULT_MIN_TURN_WORDS = 12
DEFAULT_MAX_TURN_WORDS = 38
DEFAULT_MIN_REMAINING_SECONDS = 1.0
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 1.5

FRAME_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2

TRIM_THRESHOLD = 450
TRIM_PAD_MS = 60

SPEAKER_CONFIG = {
    "Ramu": {
        "default_voice": "en-IN-PrabhatNeural",
    },
    "Riya": {
        "default_voice": "en-IN-NeerjaNeural",
    },
}

TOPICS = [
    {
        "name": "morning routines",
        "aspects": ["getting started", "planning the day", "energy levels", "quiet focus"],
        "examples": [
            "a short walk before breakfast",
            "writing a quick list of priorities",
            "breathing exercises and a glass of water",
            "checking the weather and packing light",
        ],
        "actions": [
            "set a simple goal for the first hour",
            "keep the phone away until after breakfast",
            "prepare clothes and essentials the night before",
            "start with a light stretch to loosen up",
        ],
        "challenges": [
            "sleeping late on busy weeks",
            "getting pulled into notifications too early",
            "rushing out without a plan",
            "skipping breakfast when time is tight",
        ],
        "benefits": [
            "more steady focus",
            "less decision fatigue",
            "a calmer start",
            "better pacing for the day",
        ],
    },
    {
        "name": "work habits",
        "aspects": ["deep focus", "meeting flow", "task switching", "time blocks"],
        "examples": [
            "protecting a two hour focus window",
            "batching small requests in the afternoon",
            "keeping notes after each call",
            "setting clear expectations for delivery",
        ],
        "actions": [
            "turn off popups during focus time",
            "set a timer for a single task",
            "review priorities before lunch",
            "close extra tabs to reduce noise",
        ],
        "challenges": [
            "back to back meetings",
            "urgent requests that break the plan",
            "too many open threads",
            "unclear ownership on tasks",
        ],
        "benefits": [
            "better quality work",
            "less stress by evening",
            "clearer progress tracking",
            "more time for learning",
        ],
    },
    {
        "name": "health and energy",
        "aspects": ["sleep quality", "hydration", "steady meals", "movement breaks"],
        "examples": [
            "keeping a fixed bedtime",
            "using a water bottle nearby",
            "a short walk after lunch",
            "light stretching in the evening",
        ],
        "actions": [
            "schedule a pause every hour",
            "eat a simple breakfast on time",
            "swap late snacks for tea",
            "keep a healthy option ready",
        ],
        "challenges": [
            "late screen time",
            "long sitting hours",
            "skipping meals when busy",
            "weekend routines drifting too much",
        ],
        "benefits": [
            "clearer thinking",
            "more stable mood",
            "consistent energy",
            "better recovery after work",
        ],
    },
    {
        "name": "family and relationships",
        "aspects": ["quality time", "listening well", "shared routines", "small check ins"],
        "examples": [
            "a short call in the evening",
            "a shared meal without distractions",
            "asking about the small wins",
            "planning a weekend walk",
        ],
        "actions": [
            "set aside a calm time to talk",
            "listen without fixing right away",
            "keep a shared calendar for plans",
            "celebrate little progress together",
        ],
        "challenges": [
            "conflicting schedules",
            "being tired after a long day",
            "missing signals when busy",
            "letting plans slip",
        ],
        "benefits": [
            "stronger trust",
            "less misunderstanding",
            "more support in tough weeks",
            "better balance overall",
        ],
    },
    {
        "name": "learning and growth",
        "aspects": ["daily practice", "feedback loops", "small experiments", "curiosity"],
        "examples": [
            "reading ten pages a day",
            "taking notes after a lesson",
            "trying a small side project",
            "asking for feedback early",
        ],
        "actions": [
            "set a tiny weekly goal",
            "write a short summary of what you learned",
            "practice for twenty minutes a day",
            "save useful links in one place",
        ],
        "challenges": [
            "getting stuck without guidance",
            "losing consistency during busy weeks",
            "switching topics too quickly",
            "overthinking the perfect plan",
        ],
        "benefits": [
            "steady improvement",
            "more confidence",
            "better problem solving",
            "more options for the future",
        ],
    },
    {
        "name": "money and planning",
        "aspects": ["monthly budgets", "saving habits", "emergency funds", "simple tracking"],
        "examples": [
            "setting aside a fixed amount each month",
            "tracking subscriptions once a week",
            "keeping a small buffer for surprises",
            "using one note for expenses",
        ],
        "actions": [
            "review expenses at the end of the week",
            "cancel unused services",
            "set a savings reminder",
            "separate needs from wants",
        ],
        "challenges": [
            "impulse buys during sales",
            "forgetting small recurring fees",
            "irregular income months",
            "unexpected repairs",
        ],
        "benefits": [
            "more peace of mind",
            "clearer priorities",
            "less stress about surprises",
            "space for bigger goals",
        ],
    },
    {
        "name": "travel and breaks",
        "aspects": ["short trips", "packing light", "planning routes", "resting well"],
        "examples": [
            "a weekend visit to a nearby town",
            "carrying only what you need",
            "choosing one main place to explore",
            "slowing down instead of rushing",
        ],
        "actions": [
            "plan one highlight per day",
            "leave extra time for rest",
            "pack a small first aid kit",
            "avoid overbooking activities",
        ],
        "challenges": [
            "last minute changes",
            "fatigue from tight schedules",
            "unexpected delays",
            "overpacking",
        ],
        "benefits": [
            "better memories",
            "less stress on the road",
            "more time to notice details",
            "a refreshed mind",
        ],
    },
    {
        "name": "food and cooking",
        "aspects": ["simple recipes", "healthy balance", "meal prep", "shared meals"],
        "examples": [
            "a quick lentil soup",
            "fresh vegetables with light spices",
            "prepping lunch the night before",
            "trying one new dish each week",
        ],
        "actions": [
            "keep staples ready",
            "cook in small batches",
            "limit heavy snacks late at night",
            "drink water before meals",
        ],
        "challenges": [
            "eating late after work",
            "too many processed snacks",
            "lack of time to cook",
            "skipping meals when busy",
        ],
        "benefits": [
            "steady energy",
            "better digestion",
            "more enjoyment of food",
            "less waste",
        ],
    },
    {
        "name": "technology and balance",
        "aspects": ["screen time", "notifications", "focus tools", "digital clutter"],
        "examples": [
            "setting do not disturb in the evening",
            "cleaning up unused apps",
            "using a timer for focused sessions",
            "keeping one inbox for tasks",
        ],
        "actions": [
            "turn off non essential alerts",
            "schedule a daily cleanup",
            "keep a short list of must have apps",
            "separate work and personal time",
        ],
        "challenges": [
            "constant pings",
            "too many channels to check",
            "losing focus while browsing",
            "late night scrolling",
        ],
        "benefits": [
            "more calm",
            "better sleep",
            "clearer attention",
            "better boundaries",
        ],
    },
    {
        "name": "community and support",
        "aspects": ["helping neighbors", "sharing skills", "local events", "volunteering"],
        "examples": [
            "joining a local clean up drive",
            "helping someone with a small task",
            "teaching a simple skill",
            "checking on an elderly neighbor",
        ],
        "actions": [
            "offer help once a week",
            "stay connected to local groups",
            "share resources when you can",
            "show up on time for community plans",
        ],
        "challenges": [
            "finding time to participate",
            "coordination across schedules",
            "feeling unsure how to start",
            "staying consistent",
        ],
        "benefits": [
            "stronger connections",
            "a sense of purpose",
            "practical help when needed",
            "a better neighborhood vibe",
        ],
    },
    {
        "name": "hobbies and creativity",
        "aspects": ["music practice", "writing notes", "drawing", "craft work"],
        "examples": [
            "a few minutes with a guitar",
            "sketching in a small notebook",
            "writing down ideas after dinner",
            "making something with your hands",
        ],
        "actions": [
            "keep supplies visible",
            "practice in short focused bursts",
            "share progress with a friend",
            "join a local or online group",
        ],
        "challenges": [
            "feeling rusty after a break",
            "perfectionism slowing you down",
            "limited time after work",
            "not knowing what to try next",
        ],
        "benefits": [
            "relaxation and joy",
            "fresh ideas",
            "better mood",
            "a stronger sense of identity",
        ],
    },
    {
        "name": "future planning",
        "aspects": ["long term goals", "small milestones", "risk planning", "steady progress"],
        "examples": [
            "saving for a course",
            "planning a family trip",
            "building a safety buffer",
            "choosing one goal for the quarter",
        ],
        "actions": [
            "write down the next small step",
            "review goals at the end of each month",
            "stay flexible with the plan",
            "track progress with simple notes",
        ],
        "challenges": [
            "feeling overwhelmed by big goals",
            "changing priorities",
            "losing focus over time",
            "waiting for perfect timing",
        ],
        "benefits": [
            "clear direction",
            "steady progress",
            "more confidence",
            "less uncertainty",
        ],
    },
]

SHORT_OPENERS = [
    "{listener}, on {topic}, I focus on {aspect}.",
    "On {topic}, I start with a simple step: {action}.",
    "For {topic}, I lean on {example}.",
    "About {topic}, I pay attention to {aspect}.",
]

SHORT_FOLLOWUPS = [
    "That helps with {challenge}.",
    "It gives me {benefit}.",
    "It keeps the pace calm.",
    "It is a small step that works.",
    "I keep it simple and steady.",
]

SHORT_QUESTIONS = [
    "How do you handle {aspect}?",
    "Do you also use this step: {action}?",
    "What helps with {challenge}?",
    "Have you tried {example}?",
]

SPEAKER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 ._-]{0,40})\s*[:\-]\s*(.*)$", re.IGNORECASE)


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def word_count(text: str) -> int:
    return len(text.split())


def format_timestamp(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def normalize_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    line = line.replace("**", "").replace("__", "")
    line = re.sub(r"^[\s>*-]+", "", line)
    line = re.sub(
        r"^\[?\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?\]?\s*(?:min|minutes)?\s*",
        "",
        line,
        flags=re.IGNORECASE,
    )
    return line.strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if re.match(r"^\d{1,2}:\d{2}(\s*-\s*\d{1,2}:\d{2})?$", line):
        return True
    if line.lower() in ("min", "minute", "minutes"):
        return True
    if re.match(r"^(part|segment|chapter|section)\b", line, re.IGNORECASE):
        return True
    lower = line.lower()
    if lower.startswith(("---", "###", "##", "#", "topic:", "characters:", "setting:", "estimated")):
        return True
    if lower.startswith("end of script"):
        return True
    if line.startswith("(") and line.endswith(")"):
        return True
    if line.startswith("[") and line.endswith("]"):
        return True
    if "sound fx" in lower:
        return True
    return False


def clean_dialogue_text(text: str) -> str:
    text = text.strip().replace("**", "")
    text = re.sub(r"^\([^)]*\)\s*", "", text)
    text = re.sub(r"^\[[^]]*\]\s*", "", text)
    text = re.sub(
        r"^\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?\s*(?:min|minutes)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("\u2026", "")
    text = re.sub(r"\.{3,}", "", text)
    text = text.replace("*", "").replace("#", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_speaker(raw: str) -> str:
    raw_lower = raw.lower()
    if raw_lower == "raju":
        return "Riya"
    if raw_lower == "riya":
        return "Riya"
    if raw_lower == "ramu":
        return "Ramu"
    return raw.capitalize()


def is_noise_speaker_name(name: str) -> bool:
    if re.match(r"^(part|segment|chapter|section|intro|outro|topic)\b", name, re.IGNORECASE):
        return True
    if re.match(r"^\d+$", name):
        return True
    return False


def extract_turns(text: str) -> list[dict]:
    turns: list[dict] = []
    current = None
    skip_section = False
    speaker_map: dict[str, str] = {}
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            skip_section = False
            continue
        line = normalize_line(raw_line)
        if not line:
            continue
        if re.match(r"(?i)^characters\b", line):
            skip_section = True
            continue
        if skip_section:
            if not SPEAKER_RE.search(line):
                continue
            skip_section = False
        if is_noise_line(line):
            continue
        match = SPEAKER_RE.search(line)
        if match:
            raw_speaker = match.group(1).strip()
            if is_noise_speaker_name(raw_speaker):
                current = None
                continue
            normalized = normalize_speaker(raw_speaker)
            if normalized in ("Ramu", "Riya"):
                speaker = normalized
            else:
                key = raw_speaker.lower()
                if key not in speaker_map:
                    if len(speaker_map) >= 2:
                        current = None
                        continue
                    speaker_map[key] = "Ramu" if len(speaker_map) == 0 else "Riya"
                speaker = speaker_map[key]
            content = clean_dialogue_text(match.group(2) or "")
            if content:
                entry = {"speaker": speaker, "text": content}
                turns.append(entry)
                current = entry
            else:
                current = {"speaker": speaker, "text": "", "_pending": True}
            continue
        if current and not is_noise_line(line):
            content = clean_dialogue_text(line)
            if content:
                if current.get("_pending"):
                    current["text"] = content
                    current.pop("_pending", None)
                    turns.append(current)
                else:
                    current["text"] = f"{current['text']} {content}".strip()
    return turns


def split_into_sentences(text: str) -> list[str]:
    cleaned = clean_dialogue_text(text)
    if not cleaned:
        return []
    matches = re.findall(r"[^.!?]+[.!?]*", cleaned)
    if not matches:
        return [cleaned]
    return [part.strip() for part in matches if part.strip()]


def build_turns_from_plain_text(text: str) -> list[dict]:
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        line = normalize_line(raw_line)
        if not line or is_noise_line(line):
            continue
        content = clean_dialogue_text(line)
        if content:
            current.append(content)
    if current:
        paragraphs.append(" ".join(current))

    if not paragraphs:
        return []

    sentences: list[str] = []
    for paragraph in paragraphs:
        sentences.extend(split_into_sentences(paragraph))

    if not sentences:
        return []

    min_words = DEFAULT_MIN_TURN_WORDS
    max_words = DEFAULT_MAX_TURN_WORDS
    chunks: list[str] = []
    buffer: list[str] = []
    word_total = 0

    def flush() -> None:
        nonlocal buffer, word_total
        if not buffer:
            return
        chunk = " ".join(buffer).strip()
        if chunk:
            chunks.append(chunk)
        buffer = []
        word_total = 0

    for sentence in sentences:
        cleaned = clean_dialogue_text(sentence)
        if not cleaned:
            continue
        words = cleaned.split()
        if not words:
            continue
        if len(words) > max_words:
            flush()
            for idx in range(0, len(words), max_words):
                slice_text = " ".join(words[idx : idx + max_words]).strip()
                if slice_text:
                    chunks.append(slice_text)
            continue
        if word_total + len(words) > max_words and buffer:
            flush()
        buffer.append(cleaned)
        word_total += len(words)
        if word_total >= min_words:
            flush()
    flush()

    if not chunks:
        return []

    turns: list[dict] = []
    speaker = "Ramu"
    for chunk in chunks:
        turns.append({"speaker": speaker, "text": chunk})
        speaker = "Riya" if speaker == "Ramu" else "Ramu"
    return turns


def build_turn_text(rng: random.Random, speaker: str, listener: str, topic: dict, target_words: int) -> str:
    sentences = []
    sentences.append(
        rng.choice(SHORT_OPENERS).format(
            listener=listener,
            topic=topic["name"],
            aspect=rng.choice(topic["aspects"]),
            action=rng.choice(topic["actions"]),
            example=rng.choice(topic["examples"]),
        )
    )

    while word_count(" ".join(sentences)) < target_words - 6 and len(sentences) < 3:
        if len(sentences) == 1:
            sentences.append(
                rng.choice(SHORT_FOLLOWUPS).format(
                    challenge=rng.choice(topic["challenges"]),
                    benefit=rng.choice(topic["benefits"]),
                )
            )
        else:
            sentences.append(
                rng.choice(SHORT_QUESTIONS).format(
                    aspect=rng.choice(topic["aspects"]),
                    action=rng.choice(topic["actions"]),
                    challenge=rng.choice(topic["challenges"]),
                    example=rng.choice(topic["examples"]),
                )
            )

    text = " ".join(sentences)
    if word_count(text) > target_words and len(sentences) > 1:
        sentences.pop()
        text = " ".join(sentences)
    words = text.split()
    if len(words) > target_words:
        text = " ".join(words[:target_words])
        if not text.endswith("."):
            text = text.rstrip(",") + "."
    return text


def trim_silence(frames: bytes, threshold: int, pad_frames: int) -> tuple[bytes, int]:
    if not frames:
        return frames, 0
    samples = array("h")
    samples.frombytes(frames)
    if not samples:
        return frames, 0

    start = 0
    end = len(samples)
    while start < end and abs(samples[start]) <= threshold:
        start += 1
    while end > start and abs(samples[end - 1]) <= threshold:
        end -= 1

    if start >= end:
        return b"", 0

    start = max(0, start - pad_frames)
    end = min(len(samples), end + pad_frames)
    trimmed = samples[start:end]
    return trimmed.tobytes(), len(trimmed)


async def synthesize_to_wav(
    text: str,
    voice: str,
    rate: str,
    mp3_path: Path,
    wav_path: Path,
    ffmpeg_exe: str,
    max_retries: int,
    retry_delay: float,
) -> None:
    attempt = 0
    while True:
        try:
            if mp3_path.exists():
                mp3_path.unlink(missing_ok=True)
            if wav_path.exists():
                wav_path.unlink(missing_ok=True)
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
            await communicate.save(str(mp3_path))
            subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-i",
                    str(mp3_path),
                    "-ar",
                    str(FRAME_RATE),
                    "-ac",
                    str(CHANNELS),
                    "-f",
                    "wav",
                    str(wav_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not wav_path.exists() or wav_path.stat().st_size == 0:
                raise RuntimeError("Empty wav output.")
            return
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            jitter = random.uniform(0, 0.6)
            wait_time = retry_delay * (1.6 ** (attempt - 1)) + jitter
            print(f"Retry {attempt}/{max_retries} after error: {exc}")
            await asyncio.sleep(wait_time)


def read_wav_frames(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() != CHANNELS:
            raise ValueError(f"Unexpected channels in {path}")
        if wav_file.getsampwidth() != SAMPLE_WIDTH:
            raise ValueError(f"Unexpected sample width in {path}")
        if wav_file.getframerate() != FRAME_RATE:
            raise ValueError(f"Unexpected frame rate in {path}")
        frames = wav_file.readframes(wav_file.getnframes())
        return frames, wav_file.getnframes()


def get_silence(silence_cache: dict, frame_count: int) -> bytes:
    if frame_count <= 0:
        return b""
    if frame_count not in silence_cache:
        silence_cache[frame_count] = b"\x00" * (frame_count * SAMPLE_WIDTH * CHANNELS)
    return silence_cache[frame_count]


def estimate_target_words(
    target_seconds: float,
    words_per_second: float,
    min_words: int,
    max_words: int,
) -> int:
    return clamp(int(target_seconds * words_per_second), min_words, max_words)


def resolve_minutes(args_minutes: int | None) -> int:
    if args_minutes is not None:
        return args_minutes
    return DEFAULT_MINUTES


async def run_generation(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    voice_ids = {
        "Ramu": args.ramu_voice or SPEAKER_CONFIG["Ramu"]["default_voice"],
        "Riya": args.riya_voice or SPEAKER_CONFIG["Riya"]["default_voice"],
    }

    script_turns = None
    if args.script:
        script_path = Path(args.script)
        script_text = script_path.read_text(encoding="utf-8")
        script_turns = extract_turns(script_text)
        if not script_turns:
            script_turns = build_turns_from_plain_text(script_text)
        if not script_turns:
            raise ValueError("No usable text found in the script.")

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    ramu_path = output_dir / "Ramu_Audio.wav"
    riya_path = output_dir / "Riya_Audio.wav"

    silence_cache: dict[int, bytes] = {}
    dialogue_entries = []
    words_per_second = {
        "Ramu": args.words_per_second,
        "Riya": args.words_per_second,
    }

    trim_pad_frames = int((TRIM_PAD_MS / 1000) * FRAME_RATE)

    with wave.open(str(ramu_path), "wb") as ramu_wav, wave.open(str(riya_path), "wb") as riya_wav:
        for wav_file in (ramu_wav, riya_wav):
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(FRAME_RATE)

        total_frames = 0

        def append_turn(
            speaker: str,
            text: str,
            frames: bytes,
            frame_count: int,
            start_frames: int,
            trimmed: bool,
        ) -> int:
            if speaker == "Ramu":
                ramu_wav.writeframes(frames)
                riya_wav.writeframes(get_silence(silence_cache, frame_count))
            else:
                riya_wav.writeframes(frames)
                ramu_wav.writeframes(get_silence(silence_cache, frame_count))

            if frame_count > 0:
                actual_seconds = frame_count / FRAME_RATE
                actual_wps = word_count(text) / actual_seconds
                words_per_second[speaker] = (words_per_second[speaker] * 0.7) + (actual_wps * 0.3)

            start_seconds = int(start_frames / FRAME_RATE)
            entry = {
                "start_time": format_timestamp(start_seconds),
                "speaker": speaker,
                "text": text,
                "speech_seconds": round(frame_count / FRAME_RATE, 2),
                "trimmed": trimmed,
            }
            dialogue_entries.append(entry)
            return frame_count

        async def process_turn(
            speaker: str,
            text: str,
            start_frames: int,
            turn_index: int,
            max_frames: int | None,
        ) -> int:
            mp3_path = temp_dir / f"{speaker.lower()}_{turn_index:05d}.mp3"
            wav_path = temp_dir / f"{speaker.lower()}_{turn_index:05d}.wav"

            await synthesize_to_wav(
                text=text,
                voice=voice_ids[speaker],
                rate=args.rate,
                mp3_path=mp3_path,
                wav_path=wav_path,
                ffmpeg_exe=ffmpeg_exe,
                max_retries=args.max_retries,
                retry_delay=args.retry_delay,
            )

            frames, frame_count = read_wav_frames(wav_path)
            frames, frame_count = trim_silence(frames, TRIM_THRESHOLD, trim_pad_frames)

            trimmed = False
            if max_frames is not None and frame_count > max_frames:
                frames = frames[: max_frames * SAMPLE_WIDTH * CHANNELS]
                frame_count = max_frames
                trimmed = True

            frame_count = append_turn(speaker, text, frames, frame_count, start_frames, trimmed)

            if not args.keep_temp:
                mp3_path.unlink(missing_ok=True)
                wav_path.unlink(missing_ok=True)

            return frame_count

        async def synthesize_turn(turn_index: int, turn: dict) -> dict:
            speaker = turn["speaker"]
            text = turn["text"]
            mp3_path = temp_dir / f"{speaker.lower()}_{turn_index:05d}.mp3"
            wav_path = temp_dir / f"{speaker.lower()}_{turn_index:05d}.wav"

            await synthesize_to_wav(
                text=text,
                voice=voice_ids[speaker],
                rate=args.rate,
                mp3_path=mp3_path,
                wav_path=wav_path,
                ffmpeg_exe=ffmpeg_exe,
                max_retries=args.max_retries,
                retry_delay=args.retry_delay,
            )
            return {
                "index": turn_index,
                "speaker": speaker,
                "text": text,
                "mp3_path": mp3_path,
                "wav_path": wav_path,
            }

        if script_turns is not None:
            max_concurrent = max(1, args.max_concurrent)
            if max_concurrent > 1:
                semaphore = asyncio.Semaphore(max_concurrent)

                async def run_task(index: int, turn: dict) -> dict:
                    async with semaphore:
                        return await synthesize_turn(index, turn)

                tasks = [asyncio.create_task(run_task(i, turn)) for i, turn in enumerate(script_turns)]
                results = await asyncio.gather(*tasks)
                results.sort(key=lambda item: item["index"])

                for result in results:
                    frames, frame_count = read_wav_frames(result["wav_path"])
                    frames, frame_count = trim_silence(frames, TRIM_THRESHOLD, trim_pad_frames)
                    frame_count = append_turn(
                        result["speaker"],
                        result["text"],
                        frames,
                        frame_count,
                        total_frames,
                        False,
                    )
                    total_frames += frame_count

                    if not args.keep_temp:
                        result["mp3_path"].unlink(missing_ok=True)
                        result["wav_path"].unlink(missing_ok=True)
            else:
                for turn_index, turn in enumerate(script_turns):
                    frame_count = await process_turn(
                        speaker=turn["speaker"],
                        text=turn["text"],
                        start_frames=total_frames,
                        turn_index=turn_index,
                        max_frames=None,
                    )
                    total_frames += frame_count
            print(f"Done. Total duration: {round(total_frames / FRAME_RATE, 2)}s")
        else:
            segment_frames = SEGMENT_SECONDS * FRAME_RATE
            min_remaining_frames = int(args.min_remaining_seconds * FRAME_RATE)
            total_minutes = resolve_minutes(args.minutes)

            for minute in range(total_minutes):
                minute_frames = 0
                turn_index = 0
                speaker = "Ramu"
                base_turns = args.turns_per_minute
                max_turns = max(base_turns, args.turns_per_minute + 2)

                while turn_index < max_turns:
                    remaining_frames = segment_frames - minute_frames
                    if remaining_frames <= min_remaining_frames:
                        break
                    remaining_seconds = remaining_frames / FRAME_RATE
                    turns_left = max(base_turns - turn_index, 1)
                    target_seconds = min(remaining_seconds / turns_left, SEGMENT_SECONDS / base_turns)
                    if remaining_seconds < (args.min_turn_words / words_per_second[speaker]):
                        break
                    target_words = estimate_target_words(
                        target_seconds,
                        words_per_second[speaker],
                        args.min_turn_words,
                        args.max_turn_words,
                    )
                    topic = TOPICS[(minute // 4) % len(TOPICS)]
                    listener = "Riya" if speaker == "Ramu" else "Ramu"
                    text = build_turn_text(rng, speaker, listener, topic, target_words)

                    frame_count = await process_turn(
                        speaker=speaker,
                        text=text,
                        start_frames=total_frames,
                        turn_index=(minute * max_turns) + turn_index,
                        max_frames=remaining_frames,
                    )

                    minute_frames += frame_count
                    total_frames += frame_count
                    turn_index += 1
                    speaker = "Riya" if speaker == "Ramu" else "Ramu"

                remaining_frames = segment_frames - minute_frames
                if remaining_frames > 0:
                    silence = get_silence(silence_cache, remaining_frames)
                    ramu_wav.writeframes(silence)
                    riya_wav.writeframes(silence)
                    total_frames += remaining_frames

                print(f"Minute {minute + 1}/{total_minutes} done.")

    script_txt = output_dir / "dialogue.txt"
    with script_txt.open("w", encoding="utf-8") as handle:
        for entry in dialogue_entries:
            handle.write(f"{entry['start_time']} {entry['speaker']}: {entry['text']}\n")

    script_json = output_dir / "dialogue.json"
    with script_json.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "duration_seconds": round(total_frames / FRAME_RATE, 2),
                "voices": voice_ids,
                "rate": args.rate,
                "turns_per_minute": args.turns_per_minute,
                "entries": dialogue_entries,
            },
            handle,
            indent=2,
        )

    print("Files written to:", output_dir.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate aligned speaker audio.")
    parser.add_argument("--minutes", type=int, default=None)
    parser.add_argument("--rate", default=DEFAULT_RATE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", default="speaker-audio")
    parser.add_argument("--ramu-voice", default=None)
    parser.add_argument("--riya-voice", dest="riya_voice", default=None)
    parser.add_argument("--raju-voice", dest="riya_voice", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--script", default=None)
    parser.add_argument("--turns-per-minute", type=int, default=DEFAULT_TURNS_PER_MINUTE)
    parser.add_argument("--words-per-second", type=float, default=DEFAULT_WORDS_PER_SECOND)
    parser.add_argument("--min-turn-words", type=int, default=DEFAULT_MIN_TURN_WORDS)
    parser.add_argument("--max-turn-words", type=int, default=DEFAULT_MAX_TURN_WORDS)
    parser.add_argument("--min-remaining-seconds", type=float, default=DEFAULT_MIN_REMAINING_SECONDS)
    parser.add_argument("--max-concurrent", type=int, default=DEFAULT_MAX_CONCURRENT)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY_SECONDS)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    if args.min_turn_words > args.max_turn_words:
        raise ValueError("min-turn-words must be <= max-turn-words")

    asyncio.run(run_generation(args))


if __name__ == "__main__":
    main()
