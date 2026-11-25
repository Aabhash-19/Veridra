from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import get_settings


def run_migrations(database_url: str | None = None) -> None:
    """Run Alembic migrations up to head for the configured database URL."""
    settings = get_settings()
    backend_dir = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    command.upgrade(alembic_cfg, "head")
