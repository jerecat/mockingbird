from __future__ import annotations

import ast
from pathlib import Path


def _string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_core_has_no_project_or_backend_specific_literals():
    root = Path(__file__).parents[1] / "src" / "regorch"
    core = [
        root / "models.py",
        root / "contracts.py",
        root / "context.py",
        root / "selection.py",
        root / "scheduler.py",
        root / "lifecycle.py",
    ]
    forbidden = {
        "git",
        "svn",
        "ls",
        "rm",
        "mkdir",
        "vcs",
        "qemu",
        "slurm",
        "lsf",
        "demo_linux",
    }
    literals = set().union(*(_string_literals(path) for path in core))
    assert literals.isdisjoint(forbidden)
