"""Keep each test's user-level plan registry isolated, including child CLIs."""
import pytest


@pytest.fixture(autouse=True)
def isolated_plan_registry(tmp_path, monkeypatch):
    # Do not create the directory: read-only and cancelled commands must stay so.
    monkeypatch.setenv("MB_STATE_DIR", str(tmp_path / "mb-state"))
