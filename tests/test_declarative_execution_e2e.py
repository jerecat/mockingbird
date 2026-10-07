from __future__ import annotations

from pathlib import Path

import yaml

from mockingbird import lifecycle
from mockingbird.context import load_definition, prepare


def test_declarative_contract_runs_without_project_python(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    runner = tmp_path / "run.sh"
    runner.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$1\" >> submitted.txt\n"
        "exit 0\n"
    )
    runner.chmod(0o755)

    collector = tmp_path / "collect.sh"
    collector.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  pass) status=PASS ;;\n"
        "  fail) status=FAIL ;;\n"
        "  *) status=ERROR ;;\n"
        "esac\n"
        "printf '{\"status\":\"%s\",\"artifacts\":[\"artifact://%s\"]}\\n' \"$status\" \"$1\"\n"
    )
    collector.chmod(0o755)

    definition_path = tmp_path / "regression.yaml"
    definition_path.write_text(
        yaml.safe_dump(
            {
                "name": "declarative-e2e",
                "sources": [],
                "execution": {
                    "command": ["./run.sh"],
                    "timeout_s": 5,
                    "jobs": ["pass", "fail"],
                    "collect": {
                        "command": ["./collect.sh"],
                        "timeout_s": 5,
                    },
                },
                "scheduler": {
                    "capacity_provider": "fixed",
                    "max_parallel": 1,
                    "poll_interval_s": 0.01,
                    "config": {"slots": 1},
                },
            }
        )
    )

    defn = load_definition(definition_path)
    context = prepare(defn)
    assert context["execution"]["adapter"] == "command"

    lifecycle.setup(defn)
    plan = lifecycle.create_plan(defn)
    assert [item["id"] for item in plan["jobs"]] == ["pass", "fail"]

    executions, run_dir, _ = lifecycle.run(defn)
    assert [item.job_id for item in executions] == ["pass", "fail"]
    assert (tmp_path / "submitted.txt").read_text().splitlines() == ["pass", "fail"]

    result, _ = lifecycle.collect(defn, run_dir)
    assert result["summary"] == {
        "total": 2,
        "pass": 1,
        "fail": 1,
        "error": 0,
        "skip": 0,
        "pending": 0,
        "uncollected": 0,
        "collection_error": 0,
    }
    assert [item["artifacts"] for item in result["tests"]] == [
        ["artifact://pass"],
        ["artifact://fail"],
    ]

