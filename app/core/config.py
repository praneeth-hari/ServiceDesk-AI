from datetime import time
from typing import Any
import zoneinfo
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    PROJECT_NAME: str = "HelpDesk API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "mysql+pymysql://helpdesk:helpdesk_password@localhost:3306/helpdesk_db"

    # JWT Authentication settings (placeholder by default; override in production via .env)
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Application logging level
    LOG_LEVEL: str = "INFO"

    # Business-Hours SLA Settings
    WORK_TIMEZONE: str = "Asia/Kolkata"
    WORK_DAY_START: str = "09:00"
    WORK_DAY_END: str = "18:00"
    WORK_DAYS: list[int] = [0, 1, 2, 3, 4]  # Monday=0 to Friday=4

    # AI Triage and Duplicate Detection Settings
    AI_EMBEDDER: str = "hashing"
    AI_DUPLICATE_THRESHOLD: float = 0.80
    AI_MIN_SIMILARITY: float = 0.12
    AI_KNN_K: int = 5
    AI_MAX_CANDIDATES: int = 5000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("WORK_DAYS", mode="before")
    @classmethod
    def parse_work_days(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                return json.loads(v_str)
            return [int(x.strip()) for x in v_str.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def validate_business_hours_config(self) -> "Settings":
        # 1. Valid timezone
        try:
            zoneinfo.ZoneInfo(self.WORK_TIMEZONE)
        except Exception as exc:
            raise ValueError(f"Invalid WORK_TIMEZONE '{self.WORK_TIMEZONE}': {exc}") from exc

        # 2. Valid work days (at least one working day, days between 0 and 6)
        if not self.WORK_DAYS:
            raise ValueError("WORK_DAYS must contain at least one working day (0=Monday to 6=Sunday).")
        for day in self.WORK_DAYS:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError(f"Invalid weekday '{day}' in WORK_DAYS. Must be integer between 0 and 6.")

        # 3. Work start and end times format and start before end
        try:
            start_parts = [int(p) for p in self.WORK_DAY_START.split(":")]
            end_parts = [int(p) for p in self.WORK_DAY_END.split(":")]
            if len(start_parts) != 2 or len(end_parts) != 2:
                raise ValueError("Format must be HH:MM")
            start_t = time(start_parts[0], start_parts[1])
            end_t = time(end_parts[0], end_parts[1])
        except Exception as exc:
            raise ValueError(f"WORK_DAY_START and WORK_DAY_END must be 'HH:MM': {exc}") from exc

        if start_t >= end_t:
            raise ValueError(
                f"WORK_DAY_START ({self.WORK_DAY_START}) must be strictly before WORK_DAY_END ({self.WORK_DAY_END})."
            )

        # 4. AI Triage Settings validation
        if self.AI_EMBEDDER not in ("hashing", "hashing-v2", "sbert"):
            raise ValueError(
                f"AI_EMBEDDER must be 'hashing', 'hashing-v2', or 'sbert', got '{self.AI_EMBEDDER}'"
            )

        if not (0.0 <= self.AI_MIN_SIMILARITY <= 1.0):
            raise ValueError(f"AI_MIN_SIMILARITY must be between 0.0 and 1.0, got {self.AI_MIN_SIMILARITY}")

        if not (0.0 <= self.AI_DUPLICATE_THRESHOLD <= 1.0):
            raise ValueError(
                f"AI_DUPLICATE_THRESHOLD must be between 0.0 and 1.0, got {self.AI_DUPLICATE_THRESHOLD}"
            )

        if self.AI_MIN_SIMILARITY > self.AI_DUPLICATE_THRESHOLD:
            raise ValueError(
                f"AI_MIN_SIMILARITY ({self.AI_MIN_SIMILARITY}) must not exceed "
                f"AI_DUPLICATE_THRESHOLD ({self.AI_DUPLICATE_THRESHOLD})"
            )

        if self.AI_KNN_K < 1:
            raise ValueError(f"AI_KNN_K must be at least 1, got {self.AI_KNN_K}")

        if self.AI_MAX_CANDIDATES < 1:
            raise ValueError(f"AI_MAX_CANDIDATES must be at least 1, got {self.AI_MAX_CANDIDATES}")

        return self



settings = Settings()

