"""The dashboard renders every tab without errors on the made-up race from test_dbt_pipeline."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.test_dbt_pipeline import warehouse  # noqa: E402, F401  (fixture)


def test_dashboard_renders(warehouse, bronze_dir, monkeypatch):  # noqa: F811
    warehouse.close()  # the app opens its own read-only connection
    monkeypatch.setenv("F1_DATA_DIR", str(bronze_dir))
    app = AppTest.from_file("../dashboard/app.py", default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Rounds"] == "1" and metrics["Crashes"] == "2" and metrics["Penalties"] == "1"
