import base64
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import shutil
import subprocess

import pytest

from scripts.video_to_frames import build_capture_batches, extract_keyframes, last_mondays, uc1_plan


def test_last_mondays_and_uc1_plan(tmp_path):
    today = datetime(2026, 9, 26, tzinfo=UTC)  # a Saturday
    assert last_mondays(3, today) == [datetime(2026, 9, 7, tzinfo=UTC), datetime(2026, 9, 14, tzinfo=UTC),
                                      datetime(2026, 9, 21, tzinfo=UTC)]
    assert last_mondays(1, datetime(2026, 9, 21, 15, tzinfo=UTC)) == [datetime(2026, 9, 14, tzinfo=UTC)]
    for n in (3, 1, 2):
        (tmp_path / f"week{n}.mp4").write_bytes(b"x")
    (tmp_path / "ground_truth.mp4").write_bytes(b"x")  # not a UC1 week recording
    plan = uc1_plan(tmp_path, today)
    assert [(p["video"].name, p["session_id"], p["monday"].day) for p in plan] == [
        ("week1.mp4", "s_w1_mon", 7), ("week2.mp4", "s_w2_mon", 14), ("week3.mp4", "s_w3_mon", 21)]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_extract_keyframes_from_a_real_video(tmp_path):
    video = tmp_path / "week1.mp4"
    # 3 s of test pattern that changes colour every second -> scene cuts
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=640x360:d=1,format=yuv420p[a];color=c=blue:s=640x360:d=1,format=yuv420p[b];"
                    "color=c=green:s=640x360:d=1,format=yuv420p[c];[a][b][c]concat=n=3:v=1:a=0",
                    str(video)], check=True)
    frames = extract_keyframes(video, tmp_path / "kf")
    assert 2 <= len(frames) <= 4 and all(f.suffix == ".webp" and f.stat().st_size > 0 for f in frames)


def test_capture_batch_body_shape_and_strictly_increasing_ts(tmp_path):
    frames = []
    for i in range(3):
        frame = tmp_path / f"f{i}.webp"
        frame.write_bytes(f"webp-{i}".encode())
        frames.append(frame)

    batches = build_capture_batches(
        user_id="u_1",
        capture_session_id="uc1-week1",
        frame_paths=frames,
        monday=datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert len(batches) == 1
    body = batches[0]
    assert set(body) == {"user_id", "capture_session_id", "source", "events", "frames"}
    assert body["user_id"] == "u_1"
    assert body["capture_session_id"] == "uc1-week1"
    assert body["source"] == "video_replay"
    assert body["events"] == []

    timestamps = []
    for i, frame in enumerate(body["frames"]):
        assert set(frame) == {"client_id", "ts", "trigger", "app", "window_title", "url_template", "image_webp_b64"}
        assert frame["app"] == "excel"
        assert frame["client_id"] == f"uc1-week1:{i:05d}"
        assert frame["trigger"] == "video_replay"
        assert frame["url_template"] is None
        assert base64.b64decode(frame["image_webp_b64"]) == f"webp-{i}".encode()
        timestamps.append(datetime.fromisoformat(frame["ts"].replace("Z", "+00:00")))

    assert timestamps == [
        datetime(2026, 9, 7, 9, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 7, 9, 0, 5, tzinfo=UTC),
        datetime(2026, 9, 7, 9, 0, 10, tzinfo=UTC),
    ]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_capture_batches_are_capped_at_500_frames(tmp_path):
    frames = []
    for i in range(501):
        frame = tmp_path / f"f{i}.webp"
        frame.write_bytes(b"x")
        frames.append(frame)

    batches = build_capture_batches(
        user_id="u_1",
        capture_session_id="uc1-week1",
        frame_paths=frames,
        monday=datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert [len(batch["frames"]) for batch in batches] == [500, 1]
    assert batches[1]["frames"][0]["client_id"] == "uc1-week1:00500"
