from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
MAX_FRAMES_PER_SEC = 1
MAX_FRAMES_PER_SESSION = 300
FRAME_AFTER_CLICK_MS = 400
BURST_END_IDLE_MS = 800
HEARTBEAT_S = 5
BATCH_POST_S = 5
DHASH_MAX_HAMMING = 6
REGION_DIFF_MIN = 0.02
FUSION_WINDOW_S = 1.5
NN_LABEL_COPY_MIN = 0.93
VLM_BATCH = 8
VLM_MIN_CONFIDENCE = 0.6
VOCAB_ALIAS_MIN = 0.88
VOCAB_PROMOTE_AFTER = 3
FRAMES_TTL_DAYS = 7
OBS_TTL_DAYS = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    stub_mode: bool = True
    mongodb_uri: str = ""
    db_name: str = "toolsmith"
    demo_user_id: str = "u_1"
    capture_allowed_origins: str = "http://localhost:8081"
    web_allowed_origins: str = "http://localhost:3000"
    embed_model: str = "voyage-3.5"
    voyage_mm_model: str = ""

    @property
    def allowed_origins(self) -> set[str]:
        return {origin.strip().rstrip("/") for origin in self.capture_allowed_origins.split(",")}


@lru_cache
def get_settings() -> Settings:
    return Settings()
