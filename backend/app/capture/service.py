"""Phase 0 validation and acknowledgement only; no capture persistence yet."""

import base64
import binascii
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.contracts import CaptureAck, CaptureBatch
from app.fixtures import require_demo_user


def validate_batch(batch: CaptureBatch) -> None:
    if batch.source == "desktop":
        raise PermissionError("Desktop capture is outside the three-person demo scope")
    if batch.source == "chrome":
        for item in [*batch.events, *batch.frames]:
            parsed = urlsplit(item.url_template)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in get_settings().allowed_origins:
                raise PermissionError("Capture origin is not allow-listed")
    elif batch.events:
        raise ValueError("Video replay batches contain frames only")
    for frame in batch.frames:
        try:
            raw = base64.b64decode(frame.image_webp_b64, validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.format != "WEBP":
                    raise ValueError("Frame must contain a WebP image")
                image.verify()
        except (binascii.Error, UnidentifiedImageError, OSError) as exc:
            raise ValueError("Invalid base64 WebP frame") from exc


async def ingest_capture_batch(user_id: str, batch: CaptureBatch) -> CaptureAck:
    require_demo_user(user_id)
    if batch.user_id != user_id:
        raise PermissionError("Capture batch user does not match request user")
    validate_batch(batch)
    return CaptureAck(
        ui_events=len(batch.events), frames_kept=len(batch.frames), frames_dropped=0, paused=False
    )


async def fuse(user_id: str, session_id: str) -> int:
    require_demo_user(user_id)
    return 0
