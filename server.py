import json
import os
import secrets
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
import re
from urllib.parse import parse_qs, urlparse


MAX_UPLOAD_BYTES = 800 * 1024 * 1024
UPLOAD_DIR = Path("speaker-audio") / "uploads"
ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm"}


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base)
    return base or "audio_upload.bin"


class AudioRequestHandler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/generate":
            self.handle_generate()
            return
        if path == "/transcribe":
            self.handle_transcribe()
            return
        if path == "/transcribe/init":
            self.handle_transcribe_init()
            return
        if path == "/transcribe/chunk":
            self.handle_transcribe_chunk(parsed.query)
            return
        if path == "/transcribe/complete":
            self.handle_transcribe_complete()
            return
        self.send_error(404, "Not found")

    def send_json(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def read_json_body(self) -> tuple[dict | None, str | None]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return None, "Missing JSON body"
        body = self.rfile.read(length)
        try:
            return json.loads(body), None
        except json.JSONDecodeError:
            return None, "Invalid JSON"

    def write_request_body(self, file_path: Path, length: int) -> int:
        remaining = length
        written = 0
        with file_path.open("ab") as handle:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                remaining -= len(chunk)
        return written

    def audio_type_allowed(self, filename: str, content_type: str) -> bool:
        ext = Path(filename).suffix.lower()
        if ext and ext in ALLOWED_AUDIO_EXTS:
            return True
        return content_type.startswith("audio/")

    def manifest_paths(self, upload_id: str) -> tuple[Path, Path]:
        manifest_path = UPLOAD_DIR / f"{upload_id}.json"
        part_path = UPLOAD_DIR / f"{upload_id}.part"
        return manifest_path, part_path

    def load_manifest(self, upload_id: str) -> dict | None:
        manifest_path, _ = self.manifest_paths(upload_id)
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def save_manifest(self, upload_id: str, payload: dict) -> None:
        manifest_path, _ = self.manifest_paths(upload_id)
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    def run_transcription(self, file_path: Path) -> tuple[dict | None, str | None]:
        cmd = [
            sys.executable,
            "transcribe_audio.py",
            "--audio",
            str(file_path),
            "--output",
            str(file_path.with_suffix(".json")),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None, result.stderr.strip() or result.stdout.strip() or "Transcription failed"

        output_path = file_path.with_suffix(".json")
        if not output_path.exists():
            return None, "Transcription output missing"

        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None, "Invalid transcription output"
        return payload, None

    def handle_generate(self) -> None:
        payload, error = self.read_json_body()
        if error:
            self.send_error(400, error)
            return

        script_text = (payload.get("scriptText") or "").strip()
        if not script_text:
            self.send_error(400, "scriptText is required")
            return

        minutes = payload.get("minutes")
        max_concurrent = payload.get("maxConcurrent")
        output_dir = Path("speaker-audio")
        output_dir.mkdir(parents=True, exist_ok=True)
        script_path = output_dir / "dialogue_input.txt"
        script_path.write_text(script_text, encoding="utf-8")

        cmd = [
            sys.executable,
            "generate_audio.py",
            "--script",
            str(script_path),
            "--output-dir",
            str(output_dir),
        ]
        if minutes is not None:
            cmd.extend(["--minutes", str(minutes)])
        if max_concurrent is not None:
            try:
                max_concurrent_value = max(1, int(max_concurrent))
            except (TypeError, ValueError):
                max_concurrent_value = None
            if max_concurrent_value is not None:
                max_concurrent_value = min(4, max_concurrent_value)
                cmd.extend(["--max-concurrent", str(max_concurrent_value)])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.send_json(
                500,
                {
                    "status": "error",
                    "error": result.stderr.strip()
                    or result.stdout.strip()
                    or "Generation failed",
                },
            )
            return

        metadata_path = output_dir / "dialogue.json"
        minutes_value = None
        duration_seconds = None
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                duration_seconds = metadata.get("duration_seconds")
                if duration_seconds is not None:
                    minutes_value = round(duration_seconds / 60, 2)
            except json.JSONDecodeError:
                minutes_value = None

        self.send_json(
            200,
            {
                "status": "ok",
                "minutes": minutes_value,
                "duration_seconds": duration_seconds,
            },
        )

    def handle_transcribe(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self.send_error(400, "Missing audio body")
            return
        if length > MAX_UPLOAD_BYTES:
            self.send_error(413, "File too large (max 800 MB)")
            return

        filename = sanitize_filename(self.headers.get("X-Filename", "audio_upload.bin"))
        content_type = (self.headers.get("Content-Type") or "").lower()
        if not self.audio_type_allowed(filename, content_type):
            self.send_error(415, "Unsupported file type")
            return
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / f"{int(time.time())}_{filename}"

        self.write_request_body(file_path, length)

        payload, error = self.run_transcription(file_path)
        if error:
            self.send_json(500, {"status": "error", "error": error})
            return

        self.send_json(200, payload)

    def handle_transcribe_init(self) -> None:
        payload, error = self.read_json_body()
        if error:
            self.send_error(400, error)
            return
        filename = sanitize_filename(payload.get("filename", "audio_upload.bin"))
        content_type = (payload.get("content_type") or "").lower()
        expected_size = payload.get("size")
        try:
            expected_size = int(expected_size) if expected_size is not None else 0
        except (TypeError, ValueError):
            expected_size = 0

        if expected_size and expected_size > MAX_UPLOAD_BYTES:
            self.send_error(413, "File too large (max 800 MB)")
            return
        if not self.audio_type_allowed(filename, content_type):
            self.send_error(415, "Unsupported file type")
            return

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        upload_id = f"{int(time.time())}_{secrets.token_hex(6)}"
        manifest = {
            "upload_id": upload_id,
            "filename": filename,
            "expected_size": expected_size,
            "received_bytes": 0,
            "content_type": content_type,
        }
        self.save_manifest(upload_id, manifest)
        _, part_path = self.manifest_paths(upload_id)
        part_path.touch()
        self.send_json(200, {"status": "ok", "upload_id": upload_id})

    def handle_transcribe_chunk(self, query: str) -> None:
        params = parse_qs(query)
        upload_id = params.get("upload_id", [None])[0] or self.headers.get("X-Upload-Id")
        if not upload_id:
            self.send_error(400, "Missing upload_id")
            return
        manifest = self.load_manifest(upload_id)
        if not manifest:
            self.send_error(404, "Upload not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self.send_error(400, "Missing chunk body")
            return
        expected_size = manifest.get("expected_size") or 0
        received_bytes = manifest.get("received_bytes") or 0
        if expected_size and (received_bytes + length) > expected_size:
            self.send_error(413, "Chunk exceeds expected size")
            return
        if not expected_size and (received_bytes + length) > MAX_UPLOAD_BYTES:
            self.send_error(413, "File too large (max 800 MB)")
            return

        _, part_path = self.manifest_paths(upload_id)
        written = self.write_request_body(part_path, length)
        manifest["received_bytes"] = received_bytes + written
        self.save_manifest(upload_id, manifest)
        self.send_json(200, {"status": "ok", "received_bytes": manifest["received_bytes"]})

    def handle_transcribe_complete(self) -> None:
        payload, error = self.read_json_body()
        if error:
            self.send_error(400, error)
            return
        upload_id = payload.get("upload_id")
        if not upload_id:
            self.send_error(400, "Missing upload_id")
            return
        manifest = self.load_manifest(upload_id)
        if not manifest:
            self.send_error(404, "Upload not found")
            return
        expected_size = manifest.get("expected_size") or 0
        received_bytes = manifest.get("received_bytes") or 0
        if expected_size and received_bytes != expected_size:
            self.send_error(400, "Upload incomplete")
            return

        filename = manifest.get("filename") or "audio_upload.bin"
        _, part_path = self.manifest_paths(upload_id)
        if not part_path.exists():
            self.send_error(400, "Upload missing")
            return
        final_path = UPLOAD_DIR / f"{upload_id}_{filename}"
        part_path.replace(final_path)
        manifest_path, _ = self.manifest_paths(upload_id)
        manifest_path.unlink(missing_ok=True)

        result_payload, error = self.run_transcription(final_path)
        if error:
            self.send_json(500, {"status": "error", "error": error})
            return
        self.send_json(200, result_payload)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, AudioRequestHandler)
    print(f"Serving on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
