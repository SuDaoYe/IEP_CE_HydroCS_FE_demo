"""Runtime configuration for the HydroCS integrated server.

All values can be overridden with environment variables so the same code runs
on a laptop demo and on a small cloud VM without edits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # server/
ARTIFACTS_DIR = Path(os.getenv("HYDROCS_ARTIFACTS", BASE_DIR / "artifacts"))
DATA_DIR = Path(os.getenv("HYDROCS_DATA", BASE_DIR / "data"))
CACHE_DIR = Path(os.getenv("HYDROCS_CACHE", BASE_DIR / ".cache"))


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader so the demo needs no extra dependency."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


@dataclass(slots=True)
class Settings:
    """Server settings derived from the environment."""

    app_name: str = "HydroCS API"
    api_prefix: str = "/api/v1"
    database_path: Path = field(default_factory=lambda: DATA_DIR / "hydrocs.db")

    jwt_secret: str = os.getenv(
        "HYDROCS_JWT_SECRET", "hydrocs-dev-secret-change-me-0123456789abcdef"
    )
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = int(os.getenv("HYDROCS_JWT_TTL_HOURS", "168"))

    # Imagery providers -----------------------------------------------------
    tianditu_key: str = os.getenv("TIANDITU_KEY", "")
    amap_key: str = os.getenv("VITE_AMAP_KEY", os.getenv("AMAP_KEY", ""))
    tile_cache_ttl_days: int = int(os.getenv("HYDROCS_TILE_TTL_DAYS", "30"))
    tile_request_timeout: float = float(os.getenv("HYDROCS_TILE_TIMEOUT", "8"))
    tile_connect_timeout: float = float(os.getenv("HYDROCS_TILE_CONNECT_TIMEOUT", "4"))
    tile_retries: int = int(os.getenv("HYDROCS_TILE_RETRIES", "2"))
    # Tiles smaller than this are vendor placeholders ("no imagery at this zoom").
    tile_placeholder_bytes: int = int(os.getenv("HYDROCS_TILE_PLACEHOLDER_BYTES", "3500"))
    tile_placeholder_min_zoom: int = int(os.getenv("HYDROCS_TILE_PLACEHOLDER_MIN_ZOOM", "13"))
    max_mosaic_tiles: int = int(os.getenv("HYDROCS_MAX_TILES", "600"))

    # Segmentation ----------------------------------------------------------
    yolo_weights: Path = field(
        default_factory=lambda: Path(
            os.getenv("HYDROCS_WEIGHTS", ARTIFACTS_DIR / "weights" / "4.102_best.pt")
        )
    )
    yolo_imgsz: int = int(os.getenv("HYDROCS_YOLO_IMGSZ", "1024"))
    yolo_conf: float = float(os.getenv("HYDROCS_YOLO_CONF", "0.25"))
    yolo_iou: float = float(os.getenv("HYDROCS_YOLO_IOU", "0.5"))
    yolo_window: int = int(os.getenv("HYDROCS_YOLO_WINDOW", "1024"))
    yolo_overlap: int = int(os.getenv("HYDROCS_YOLO_OVERLAP", "128"))
    segment_min_area_ha: float = float(os.getenv("HYDROCS_MIN_AREA_HA", "0.01"))
    segment_cache_ttl_minutes: int = int(os.getenv("HYDROCS_SEG_CACHE_MIN", "180"))

    # Irrigation ------------------------------------------------------------
    et_grid_path: Path = field(
        default_factory=lambda: Path(os.getenv("HYDROCS_ET_GRID", ARTIFACTS_DIR / "et_grid.npz"))
    )
    era5_path: Path = field(
        default_factory=lambda: Path(os.getenv("HYDROCS_ERA5", ARTIFACTS_DIR / "era5_daily.npz"))
    )
    admin_dir: Path = field(
        default_factory=lambda: Path(os.getenv("HYDROCS_ADMIN_DIV", ARTIFACTS_DIR / "admin"))
    )
    meteo_inbox: Path = field(
        default_factory=lambda: Path(os.getenv("HYDROCS_METEO_INBOX", DATA_DIR / "meteo_inbox"))
    )
    default_efficiency: float = float(os.getenv("HYDROCS_IRRIGATION_EFFICIENCY", "0.85"))
    effective_rain_ratio: float = float(os.getenv("HYDROCS_EFFECTIVE_RAIN_RATIO", "0.0"))

    # Misc ------------------------------------------------------------------
    cors_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv(
            "HYDROCS_CORS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
        ).split(",")
        if o.strip()
    )
    seed_demo: bool = _env_flag("HYDROCS_SEED_DEMO", True)

    @property
    def has_yolo_weights(self) -> bool:
        return self.yolo_weights.is_file()

    def ensure_dirs(self) -> None:
        for path in (ARTIFACTS_DIR, DATA_DIR, CACHE_DIR, self.database_path.parent, self.meteo_inbox):
            Path(path).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
