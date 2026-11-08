import pytest

from ingestion import landing


@pytest.fixture(autouse=True)
def bronze_dir(tmp_path, monkeypatch):
    """Every test gets its own empty storage root."""
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    landing.store.cache_clear()
    yield tmp_path.resolve()
    landing.store.cache_clear()
