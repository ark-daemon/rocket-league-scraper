"""Runtime configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or `.env`."""

    model_config = SettingsConfigDict(env_prefix="RL_", env_file=".env", extra="ignore")

    db_path: Path = Path("rocketleague.db")
    export_dir: Path = Path("exports")
    log_dir: Path = Path("logs")

    blast_base_url: HttpUrl
    blast_api_base_url: HttpUrl
    liquipedia_base_url: HttpUrl
    drekt_csv_urls: tuple[HttpUrl, ...]

    http_timeout_seconds: float = 30.0
    blast_rate_limit_seconds: float = 0.75
    liquipedia_rate_limit_seconds: float = 2.0
    spreadsheet_rate_limit_seconds: float = 0.25
    max_concurrency: int = 6
    blast_fingerprint_seed: int
    blast_probe_deep_stats: bool = False
    blast_max_discovered_tournaments: int = 16

    user_agent: str

    rlcs_regions: tuple[str, ...] = ("NA", "EU", "SAM", "OCE", "MENA", "APAC", "SSA")
    blast_tournament_slugs: tuple[str, ...]
    liquipedia_seed_pages: tuple[str, ...]

    @field_validator(
        "drekt_csv_urls",
        "blast_tournament_slugs",
        "liquipedia_seed_pages",
        "rlcs_regions",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, v: object) -> list[str] | object:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
