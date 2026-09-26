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
    app: str = "excel",
    window_title: str | None = None,
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
                    "app": app,
                    "window_title": window_title,
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


VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


def last_mondays(n: int, today: datetime | None = None) -> list[datetime]:
    """The n most recent Mondays strictly before `today`, oldest first (week 1 = oldest)."""
    today = _as_utc(today or datetime.now(UTC)).replace(hour=0, minute=0, second=0, microsecond=0)
    back = today.weekday() or 7
    latest = today - timedelta(days=back)
    return [latest - timedelta(weeks=n - 1 - i) for i in range(n)]


def uc1_plan(video_dir: Path, today: datetime | None = None) -> list[dict[str, Any]]:
    """week1..weekN videos -> one session per past Monday: s_w1_mon, s_w2_mon, ... (the ids the
    UC1 fixture uses as evidence_session_ids, and the names of hand-label files)."""
    videos = sorted(p for p in video_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS and "week" in p.stem.lower())
    if not videos:
        raise FileNotFoundError(f"no week*.mp4/mov/mkv/webm recordings in {video_dir}")
    mondays = last_mondays(len(videos), today)
    return [{"video": v, "session_id": f"s_w{i}_mon", "monday": m, "window_title": f"sales_w{i}.xlsx - Excel"}
            for i, (v, m) in enumerate(zip(videos, mondays, strict=True), start=1)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Excel recordings -> keyframes -> POST /capture/batch")
    parser.add_argument("video", type=Path, nargs="?", help="one recording (or use --uc1 DIR)")
    parser.add_argument("--uc1", type=Path, help="dir with week1..3 recordings; backdates each to a past Monday")
    parser.add_argument("--out", type=Path, default=Path("data/recordings/uc1/keyframes"))
    parser.add_argument("--user-id", default="u_1")
    parser.add_argument("--capture-session-id")
    parser.add_argument("--monday", help="ISO date of the Monday to backdate to (single video)")
    parser.add_argument("--api-base", help="post to <api>/capture/batch; omit to print the bodies")
    parser.add_argument("--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD)
    args = parser.parse_args()

    if args.uc1:
        plan = uc1_plan(args.uc1)
    elif args.video and args.monday:
        plan = [{"video": args.video, "session_id": args.capture_session_id or args.video.stem,
                 "monday": datetime.fromisoformat(args.monday), "window_title": None}]
    else:
        parser.error("give a video + --monday, or --uc1 DIR")

    results = []
    for item in plan:
        frames = extract_keyframes(item["video"], args.out / item["session_id"], scene_threshold=args.scene_threshold)
        batches = build_capture_batches(user_id=args.user_id, capture_session_id=item["session_id"],
                                        frame_paths=frames, monday=item["monday"], window_title=item["window_title"])
        if args.api_base:
            acks = [post_capture_batch(args.api_base, b) for b in batches]
            results.append({"session_id": item["session_id"], "monday": item["monday"].date().isoformat(),
                            "frames": len(frames), "acks": acks})
            print(f"{item['video'].name} -> {item['session_id']} ({item['monday']:%a %Y-%m-%d}): "
                  f"{len(frames)} keyframes posted")
        else:
            results.extend(batches)
    if args.api_base:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
