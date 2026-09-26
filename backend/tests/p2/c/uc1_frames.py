"""Synthetic Excel-like keyframes for the UC1 session (week 1). Each step looks different
enough to survive dedupe, like a real dialog/ribbon change would."""
import io

from PIL import Image, ImageDraw, ImageFont

STEPS = [  # (frame text, block colour, block position)
    ("File > Open  sales_w1.xlsx  Recent workbooks", (33, 115, 70), (0, 0)),
    ("Rename columns: reg -> Region   amt -> Amount", (200, 120, 20), (1, 0)),
    ("Go To Special > Blanks > Delete Sheet Rows", (150, 40, 40), (2, 0)),
    ("Format Cells > Number > Amount as Number", (40, 60, 160), (0, 1)),
    ("Insert PivotTable  Rows: Region  Values: Sum of Amount", (90, 20, 120), (1, 1)),
    ("Insert Chart > Clustered Bar  Sum of Amount by Region", (20, 140, 150), (2, 1)),
    ("Save As > Web Page (*.html)  dashboard_w1.html", (120, 120, 20), (0, 2)),
]


def _font(size=30):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def frame_image(text, color, pos, noise=0) -> bytes:
    img = Image.new("RGB", (1280, 720), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 60], fill=(33, 115, 70))
    d.text((20, 15), "sales_w1.xlsx - Excel", fill="white", font=_font(26))
    x, y = pos
    d.rectangle([60 + x * 400, 120 + y * 190, 60 + x * 400 + 360, 120 + y * 190 + 170], fill=color)
    d.text((40, 640), text, fill="black", font=_font(30))
    if noise:
        d.point([(5 + i, 700) for i in range(noise)], fill="black")
    d.text((20, 690), "Sheet1", fill="black", font=_font(18))
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=90)
    return buf.getvalue()


def session_frames(session_id="s_w1_mon", user_id="u_1"):
    frames = []
    for i, (text, color, pos) in enumerate(STEPS):
        frames.append({"_id": f"f_{i + 1:03d}", "user_id": user_id, "session_id": session_id,
                       "ts": f"2026-09-07T09:{i:02d}:00Z", "app": "excel", "source": "video_replay",
                       "window_title": "sales_w1.xlsx - Excel", "trigger": "video_replay",
                       "image": frame_image(text, color, pos)})
    t, c, p = STEPS[4]
    frames.append({**frames[4], "_id": "f_dup", "ts": "2026-09-07T09:04:30Z", "image": frame_image(t, c, p)})
    frames.append({**frames[5], "_id": "f_near", "ts": "2026-09-07T09:05:30Z",
                   "image": frame_image(*STEPS[5], noise=3)})
    frames.append({**frames[6], "_id": "f_secret", "ts": "2026-09-07T09:07:00Z",
                   "image": frame_image("api_key = sk-live1234567890abcdefXYZ", (0, 0, 0), (1, 2))})
    return sorted(frames, key=lambda f: f["ts"])
