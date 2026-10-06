from __future__ import annotations

from pathlib import Path

import mockingbird.context as context_module


class FakeProvider:
    def __init__(self, provider_name):
        self.provider_name = provider_name

    def materialize(self, source, destination):
        destination.mkdir(parents=True, exist_ok=True)
        return {
            "resolved_revision": f"resolved-{source['revision']}",
            "provider_metadata": {"fake": self.provider_name},
        }


def test_context_accepts_unbounded_mixed_sources(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        context_module,
        "load_source_provider",
        lambda name: FakeProvider(name),
    )
    definition_file = tmp_path / "regression.yaml"
    definition_file.write_text(
        """
name: mixed
sources:
  - {name: dut, provider: alpha, url: u1, revision: r1}
  - {name: tb, provider: beta, url: u2, revision: r2}
  - {name: fw, provider: alpha, url: u3, revision: r3}
execution:
  adapter: demo_linux
  config: {tests: []}
scheduler:
  capacity_provider: fixed
  max_parallel: 1
  poll_interval_s: 0.1
  config: {slots: 1}
"""
    )
    defn = context_module.load_definition(definition_file)
    context = context_module.prepare(defn)

    assert [item["name"] for item in context["sources"]] == ["dut", "tb", "fw"]
    assert [item["provider"] for item in context["sources"]] == ["alpha", "beta", "alpha"]
    assert (tmp_path / "work" / "sources" / "dut").is_dir()
    assert Path(context["paths"]["workspace"]) == tmp_path / "work"
