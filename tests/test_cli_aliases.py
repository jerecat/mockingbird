from __future__ import annotations

import tomllib
from pathlib import Path


def test_full_cli_and_mb_alias_share_one_entry_point():
    root = Path(__file__).parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text())
    scripts = data["project"]["scripts"]
    assert scripts == {
        "mockingbird": "mockingbird.cli:main",
        "mb": "mockingbird.cli:main",
    }


def test_old_cli_name_is_not_registered():
    root = Path(__file__).parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text())
    assert "reg" not in data["project"]["scripts"]
