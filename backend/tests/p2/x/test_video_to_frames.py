import base64
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts.video_to_frames import build_capture_batches


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
        assert set(frame) == {"client_id", "ts", "trigger", "url_template", "image_webp_b64"}
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
