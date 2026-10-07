"""Serial-only policy is enforced before side effects at both entry points."""
from unittest.mock import Mock

import pytest
import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare, validate_definition
from mockingbird.io import read_json, write_json
from mockingbird.models import Job
from mockingbird.scheduler import run_jobs


INVALID = [0, -1, 2, 8, True, False, 1.0, 1.5, "1", "2", None]


@pytest.mark.parametrize("value", INVALID)
def test_definition_rejects_non_integer_one(value):
    with pytest.raises(ValueError, match="max_parallel must be the integer 1"):
        validate_definition({
            "execution": {"command": ["true"], "timeout_s": 1, "jobs": ["a"]},
            "scheduler": {"capacity_provider": "fixed", "max_parallel": value},
        })


@pytest.mark.parametrize("value", INVALID)
def test_runtime_scheduler_rejects_before_capacity_or_execution(value):
    execute = Mock()
    capacity = Mock()
    with pytest.raises(ValueError, match="max_parallel must be the integer 1"):
        run_jobs([Job("a")], execute, capacity, value, 0.01)
    execute.assert_not_called()
    capacity.available_slots.assert_not_called()


@pytest.mark.parametrize("value", [2, 1.5, "1", True])
def test_run_rejects_invalid_frozen_context_before_creating_run(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "regression.yaml"
    path.write_text(yaml.safe_dump({
        "execution": {"command": ["true"], "timeout_s": 1, "jobs": ["a"]},
        "scheduler": {"capacity_provider": "fixed", "config": {"slots": 1}},
    }))
    defn = load_definition(path)
    context = prepare(defn)
    assert context["scheduler"]["max_parallel"] == 1  # Omission is supported.
    lifecycle.setup(defn)
    lifecycle.create_plan(defn)
    context_path = tmp_path / "work/.reg/context.json"
    context = read_json(context_path)
    context["scheduler"]["max_parallel"] = value
    write_json(context_path, context)
    with pytest.raises(ValueError, match="max_parallel must be the integer 1"):
        lifecycle.run(defn)
    assert list((tmp_path / "runs").iterdir()) == []
