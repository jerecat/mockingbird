import json
import sys
from pathlib import Path

import pytest

from mockingbird.adapters.command import Adapter
from test_command_adapter import _execution_context


def context(tmp_path, **overrides):
    config = {
        "defaults": {
            "command": [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", "prefix"],
            "timeout_s": 5,
            "args_suffix": ["--mode", "regression"],
        },
        "jobs": ["inherited", {"id": "replaced", "args": ["a b", ""], "args_suffix": ["tail"]},
                 {"id": "removed", "args": [], "args_suffix": []}],
    }
    config.update(overrides)
    return {"invocation_dir": str(tmp_path), "execution": {"config": config}}


def test_suffix_order_override_clear_and_frozen_contract(tmp_path):
    adapter = Adapter()
    ctx = context(tmp_path)
    jobs = adapter.plan(ctx)
    ctx["execution"]["config"]["defaults"]["args_suffix"].append("later-edit")
    expected = [
        ["prefix", "inherited", "--mode", "regression"],
        ["prefix", "a b", "", "tail"],
        ["prefix"],
    ]
    for job, arguments in zip(jobs, expected):
        execution_context = _execution_context(tmp_path / job.id)
        result = adapter.execute(ctx, job, execution_context)
        assert result.observation["returncode"] == 0
        assert json.loads(Path(execution_context.stdout_path).read_text()) == arguments


def test_omitted_suffix_and_legacy_plan(tmp_path):
    adapter = Adapter()
    ctx = context(tmp_path)
    del ctx["execution"]["config"]["defaults"]["args_suffix"]
    job = adapter.plan(ctx)[0]
    assert job.payload["args_suffix"] == []
    del job.payload["args_suffix"]  # Contract saved by an older version.
    execution_context = _execution_context(tmp_path)
    result = adapter.execute(ctx, job, execution_context)
    assert result.observation["returncode"] == 0
    assert json.loads(Path(execution_context.stdout_path).read_text()) == ["prefix", "inherited"]


@pytest.mark.parametrize("value", [None, "--flag", [1], ["bad\0argument"], {}])
@pytest.mark.parametrize("location", ["defaults", "job"])
def test_invalid_suffix_is_rejected_at_plan(tmp_path, value, location):
    ctx = context(tmp_path)
    config = ctx["execution"]["config"]
    if location == "defaults":
        config["defaults"]["args_suffix"] = value
    else:
        config["jobs"] = [{"id": "job", "args_suffix": value}]
    with pytest.raises(ValueError, match="args_suffix"):
        Adapter().plan(ctx)


def test_shorthand_suffix(tmp_path):
    ctx = context(tmp_path)
    config = ctx["execution"]["config"]
    config["args_suffix"] = config["defaults"].pop("args_suffix")
    assert Adapter().plan(ctx)[0].payload["args_suffix"] == ["--mode", "regression"]
