from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

from mockingbird.adapters.demo_linux import Adapter as DemoLinuxAdapter
from mockingbird.adapters.selftest import Adapter as SelfTestAdapter
from mockingbird.capacity.command import Provider as CommandCapacityProvider
from mockingbird.capacity.fixed import Provider as FixedCapacityProvider
from mockingbird.contracts import CapacityProvider, ExecutionAdapter, SourceProvider
from mockingbird.plugins import load_adapter, load_capacity_provider, load_source_provider
from mockingbird.sources.git import Provider as GitSourceProvider
from mockingbird.sources.svn import Provider as SvnSourceProvider


def test_extension_contracts_have_deliberately_small_abstract_surfaces():
    assert set(ExecutionAdapter.__abstractmethods__) == {"setup", "plan", "execute", "collect"}
    assert set(SourceProvider.__abstractmethods__) == {"materialize"}
    assert set(CapacityProvider.__abstractmethods__) == {"available_slots"}


def test_all_plugin_contracts_offer_probe_for_doctor():
    assert hasattr(ExecutionAdapter, "probe")
    assert hasattr(SourceProvider, "probe")
    assert hasattr(CapacityProvider, "probe")


def test_builtin_plugins_implement_only_the_declared_boundaries():
    assert issubclass(DemoLinuxAdapter, ExecutionAdapter)
    assert issubclass(SelfTestAdapter, ExecutionAdapter)
    assert issubclass(GitSourceProvider, SourceProvider)
    assert issubclass(SvnSourceProvider, SourceProvider)
    assert issubclass(FixedCapacityProvider, CapacityProvider)
    assert issubclass(CommandCapacityProvider, CapacityProvider)


def test_external_module_class_adapter_can_be_loaded_without_editing_core(tmp_path, monkeypatch):
    module = tmp_path / "project_adapter.py"
    module.write_text(
        "from mockingbird.contracts import ExecutionAdapter\n"
        "class ProjectAdapter(ExecutionAdapter):\n"
        "    def setup(self, context): pass\n"
        "    def plan(self, context): return []\n"
        "    def execute(self, context, job, execution): raise NotImplementedError\n"
        "    def collect(self, context, executions): return []\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("project_adapter", None)
    adapter = load_adapter("project_adapter:ProjectAdapter")
    assert isinstance(adapter, ExecutionAdapter)


def test_external_plugins_are_rejected_when_they_do_not_implement_contract(tmp_path, monkeypatch):
    module = tmp_path / "not_an_adapter.py"
    module.write_text("class Thing:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("not_an_adapter", None)
    with pytest.raises(TypeError, match="ExecutionAdapter"):
        load_adapter("not_an_adapter:Thing")


def test_external_source_and_capacity_plugins_can_be_loaded_without_editing_core(tmp_path, monkeypatch):
    module = tmp_path / "project_plugins.py"
    module.write_text(
        "from mockingbird.contracts import SourceProvider, CapacityProvider\n"
        "class ProjectSource(SourceProvider):\n"
        "    def materialize(self, source, destination): return {\"resolved_revision\": \"demo\"}\n"
        "class ProjectCapacity(CapacityProvider):\n"
        "    def __init__(self, config): self.slots = int(config[\"slots\"])\n"
        "    def available_slots(self): return self.slots\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("project_plugins", None)
    source = load_source_provider("project_plugins:ProjectSource")
    capacity = load_capacity_provider("project_plugins:ProjectCapacity", {"slots": 3})
    assert isinstance(source, SourceProvider)
    assert isinstance(capacity, CapacityProvider)
    assert capacity.available_slots() == 3


def test_builtin_short_names_still_load_through_contract_checked_loader():
    assert isinstance(load_adapter("demo_linux"), ExecutionAdapter)
    assert isinstance(load_source_provider("git"), SourceProvider)
    assert isinstance(load_source_provider("svn"), SourceProvider)
    assert isinstance(load_capacity_provider("fixed", {"slots": 1}), CapacityProvider)


def test_architecture_documentation_and_adrs_are_part_of_the_repository_contract():
    root = Path(__file__).parents[1]
    required = [
        root / "Documentation" / "Architecture.md",
        root / "Documentation" / "Architecture_Contract.md",
        root / "Documentation" / "Adapter_Implementation_Guide.md",
        root / "Documentation" / "Adapter_Conformance_Testing.md",
        root / "Documentation" / "Getting_Started.md",
        root / "Documentation" / "Integration_Guide.md",
        root / "Documentation" / "Demos.md",
        *[root / "Documentation" / "ADR" / name for name in (
            "0001-context-plan-run-result.md",
            "0002-plugin-boundaries.md",
            "0003-intent-and-evidence.md",
            "0004-explicit-failed-from.md",
            "0005-execution-context-and-process-io.md",
            "0006-doctor-and-conformance-kit.md",
        )],
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    assert not missing, f"architecture documentation is missing: {missing}"


def test_contract_methods_keep_expected_call_shape():
    assert list(inspect.signature(ExecutionAdapter.probe).parameters) == ["self", "context"]
    assert list(inspect.signature(ExecutionAdapter.setup).parameters) == ["self", "context"]
    assert list(inspect.signature(ExecutionAdapter.plan).parameters) == ["self", "context"]
    assert list(inspect.signature(ExecutionAdapter.execute).parameters) == [
        "self", "context", "job", "execution"
    ]
    assert list(inspect.signature(ExecutionAdapter.collect).parameters) == ["self", "context", "executions"]
    assert list(inspect.signature(SourceProvider.probe).parameters) == ["self", "source"]
    assert list(inspect.signature(SourceProvider.materialize).parameters) == ["self", "source", "destination"]
    assert list(inspect.signature(CapacityProvider.probe).parameters) == ["self"]
    assert list(inspect.signature(CapacityProvider.available_slots).parameters) == ["self"]
