from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


MAX_FRAMES_PER_BATCH = 500
DEFAULT_SCENE_THRESHOLD = 0.02
MAX_WIDTH = 1280
WEBP_QUALITY = 70


def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    *,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg()
    pattern = output_dir / f"{video_path.stem}_%05d.webp"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select='gt(scene,{scene_threshold})',scale='min({MAX_WIDTH},iw)':-2",
            "-vsync",
            "vfr",
            "-f",
            "image2",
            "-c:v",
            "libwebp",
            "-q:v",
            str(WEBP_QUALITY),
            str(pattern),
        ],
        check=True,
    )
    frames = sorted(output_dir.glob(f"{video_path.stem}_*.webp"))
    if frames:
        return frames

    fallback = output_dir / f"{video_path.stem}_00001.webp"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({MAX_WIDTH},iw)':-2",
            "-f",
            "image2",
            "-c:v",
            "libwebp",
            "-q:v",
            str(WEBP_QUALITY),
            str(fallback),
        ],
        check=True,
    )
    return [fallback]


def build_capture_batches(
    *,
    user_id: str,
    capture_session_id: str,
    frame_paths: list[Path],
    monday: datetime,
) -> list[dict[str, Any]]:
    start = _as_utc(monday).replace(hour=9, minute=0, second=0, microsecond=0)
    batches = []
    for batch_start in range(0, len(frame_paths), MAX_FRAMES_PER_BATCH):
        chunk = frame_paths[batch_start : batch_start + MAX_FRAMES_PER_BATCH]
        frames = []
        for offset, path in enumerate(chunk, start=batch_start):
            ts = start + timedelta(seconds=offset * 5)
            frames.append(
                {
                    "client_id": f"{capture_session_id}:{offset:05d}",
                    "ts": ts.isoformat().replace("+00:00", "Z"),
                    "trigger": "video_replay",
                    "url_template": None,
                    "image_webp_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )
        batches.append(
            {
                "user_id": user_id,
                "capture_session_id": capture_session_id,
                "source": "video_replay",
                "events": [],
                "frames": frames,
            }
        )
    return batches


def post_capture_batch(api_base: str, batch: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/capture/batch",
        data=json.dumps(batch).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found on PATH")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/recordings/uc1/keyframes"))
    parser.add_argument("--user-id", default="u_1")
    parser.add_argument("--capture-session-id")
    parser.add_argument("--monday", required=True)
    parser.add_argument("--api-base")
    parser.add_argument("--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD)
    args = parser.parse_args()

    frames = extract_keyframes(args.video, args.out, scene_threshold=args.scene_threshold)
    batches = build_capture_batches(
        user_id=args.user_id,
        capture_session_id=args.capture_session_id or args.video.stem,
        frame_paths=frames,
        monday=datetime.fromisoformat(args.monday),
    )
    if args.api_base:
        print(json.dumps([post_capture_batch(args.api_base, b) for b in batches], indent=2, sort_keys=True))
    else:
        print(json.dumps(batches, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
