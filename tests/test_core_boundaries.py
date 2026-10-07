from __future__ import annotations

import ast
from pathlib import Path


CORE_FILES = [
    "context.py",
    "command_fields.py",
    "setup_contract.py",
    "errors.py",
    "status.py",
    "contracts.py",
    "io.py",
    "lifecycle.py",
    "models.py",
    "plugins.py",
    "scheduler.py",
    "selection.py",
    "cli.py",
    "doctor.py",
    "validation.py",
]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_does_not_import_specific_adapter_source_or_capacity_plugins():
    root = Path(__file__).parents[1] / "src" / "mockingbird"
    forbidden_prefixes = (
        "mockingbird.adapters",
        "mockingbird.sources",
        "mockingbird.capacity",
        "adapters.",
        "sources.",
        "capacity.",
    )

    for filename in CORE_FILES:
        imports = _imports(root / filename)
        assert not any(
            name.startswith(forbidden_prefixes) for name in imports
        ), f"{filename} leaks a concrete plugin import: {sorted(imports)}"


def test_core_does_not_spawn_project_commands_directly():
    root = Path(__file__).parents[1] / "src" / "mockingbird"
    for filename in CORE_FILES:
        imports = _imports(root / filename)
        assert "subprocess" not in imports, f"{filename} should not execute project commands"
