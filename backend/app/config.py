from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS2_", env_file=".env", extra="ignore")

    app_name: str = "CS2 Tactical Analytics API"
    debug: bool = False

    # Storage
    data_dir: Path = BASE_DIR / "data_store"
    model_dir: Path = BASE_DIR / "model_store"
    db_url: str = ""

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # First admin, auto-created on startup only when both are set (see .env)
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # HLTV scraping
    hltv_base_url: str = "https://www.hltv.org"
    request_delay_s: float = 1.5
    request_timeout_s: float = 30.0

    # GOTV archives are large (~1 GB per match), so the binary download needs a far more generous timeout than ordinary page requests
    demo_download_timeout_s: float = 600.0
    # FlareSolverr is the ONLY challenge solver for /results + demo download
    flaresolverr_url: str = ""
    # Concurrent FlareSolverr solves; keep at 1 unless you scale the solver.
    flaresolverr_concurrency: int = 1
    # max matches to downland
    hltv_max_matches: int = 100

    # When true, demo "parsing" fabricates plausible rounds instead of reading the .dem with awpy. Lets the ingestion pipeline run without real demos
    use_sample_data: bool = False

    # Parse real demos in a separate process so the CPU work doesn't stall the API.
    parse_in_subprocess: bool = True
    parse_workers: int = 1
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @property
    def resolved_db_url(self) -> str:
        return self.db_url or f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def demos_dir(self) -> Path:
        return self.data_dir / "demos"

    @property
    def dataset_dir(self) -> Path:
        return self.data_dir / "dataset"

    @property
    def replays_dir(self) -> Path:
        return self.data_dir / "replays"

    @property
    def radars_dir(self) -> Path:
        # Drop custom radar PNGs here (e.g. SimpleRadar) named ``<map_id>.png``;
        # served in preference to awpy's bundled radars.
        return self.data_dir / "radars"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.demos_dir, s.dataset_dir, s.replays_dir, s.radars_dir, s.model_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
