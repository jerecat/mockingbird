from __future__ import annotations

from pathlib import Path

import yaml

from regorch.context import load_definition, prepare


class FakeProvider:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def materialize(self, source, destination: Path):
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "materialized.txt").write_text(self.provider_name)
        return {
            "resolved_revision": f"resolved-{source.get('revision', 'HEAD')}",
            "provider_metadata": {"fake": True},
        }


def test_prepare_supports_any_number_and_mix_of_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition_path = tmp_path / "regression.yaml"
    definition_path.write_text(
        yaml.safe_dump(
            {
                "name": "mixed",
                "sources": [
                    {"name": "dut", "provider": "git", "url": "g", "revision": "main"},
                    {"name": "tb", "provider": "svn", "url": "s", "revision": "42"},
                    {"name": "fw", "provider": "git", "url": "g2", "revision": "r1"},
                ],
                "execution": {"adapter": "demo_linux", "config": {"tests": []}},
                "scheduler": {
                    "capacity_provider": "fixed",
                    "max_parallel": 2,
                    "poll_interval_s": 0.1,
                    "config": {"slots": 2},
                },
            }
        )
    )

    monkeypatch.setattr(
        "regorch.context.load_source_provider",
        lambda name: FakeProvider(name),
    )

    context = prepare(load_definition(definition_path))

    assert Path(context["paths"]["workspace"]) == tmp_path / "work"
    assert [item["name"] for item in context["sources"]] == ["dut", "tb", "fw"]
    assert [item["provider"] for item in context["sources"]] == ["git", "svn", "git"]
    assert (tmp_path / "work" / "sources" / "dut" / "materialized.txt").exists()
    assert (tmp_path / "work" / ".reg" / "context.json").exists()


def test_prepare_rejects_duplicate_source_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    definition_path = tmp_path / "regression.yaml"
    definition_path.write_text(
        yaml.safe_dump(
            {
                "sources": [
                    {"name": "same", "provider": "git", "url": "a"},
                    {"name": "same", "provider": "svn", "url": "b"},
                ],
                "execution": {"adapter": "demo_linux"},
                "scheduler": {"capacity_provider": "fixed"},
            }
        )
    )
    monkeypatch.setattr(
        "regorch.context.load_source_provider",
        lambda name: FakeProvider(name),
    )

    import pytest

    with pytest.raises(ValueError, match="duplicate source name"):
        prepare(load_definition(definition_path))
