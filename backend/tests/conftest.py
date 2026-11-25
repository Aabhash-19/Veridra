from collections.abc import Generator
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.db.migrations import run_migrations
from app.db.session import reset_engine
from app.services.event_bus import cancellation_registry


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    db_file = tmp_path / "test_veridra.db"
    chk_file = tmp_path / "test_checkpoints.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(chk_file))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("DEMO_MODE", "false")

    get_settings.cache_clear()
    reset_engine(db_url)
    run_migrations(db_url)
    yield db_file
    cancellation_registry._cancelled.clear()
    get_settings.cache_clear()
