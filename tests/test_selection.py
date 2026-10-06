from __future__ import annotations

import json

import pytest

from regorch.models import Job
from regorch.selection import Selection, select_jobs, write_selection_file


def _jobs() -> list[Job]:
    return [Job(id="a"), Job(id="b"), Job(id="c")]


def test_failed_from_is_explicit_and_records_provenance(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "run_id": "old-run",
                "tests": [
                    {"id": "a", "status": "PASS"},
                    {"id": "b", "status": "FAIL"},
                    {"id": "c", "status": "ERROR"},
                ],
            }
        )
    )

    selected, meta = select_jobs(_jobs(), Selection(failed_from=str(result)))

    assert [job.id for job in selected] == ["b"]
    assert meta["failed_from"] == str(result.resolve())
    assert meta["failed_from_run_id"] == "old-run"
    assert len(meta["failed_from_sha256"]) == 64


def test_failed_from_can_be_narrowed_by_explicit_selector(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "run_id": "old-run",
                "tests": [
                    {"id": "a", "status": "FAIL"},
                    {"id": "b", "status": "FAIL"},
                    {"id": "c", "status": "PASS"},
                ],
            }
        )
    )

    selected, _ = select_jobs(
        _jobs(), Selection(failed_from=str(result), test_ids=["b"])
    )
    assert [job.id for job in selected] == ["b"]


def test_editable_selection_file_contains_only_ids(tmp_path):
    selection_path = tmp_path / "run.txt"
    write_selection_file(selection_path, _jobs())
    text = selection_path.read_text()
    assert "a" in text and "b" in text and "c" in text

    selection_path.write_text("# edited by user\na\n\nc\n")
    selected, _ = select_jobs(_jobs(), Selection(selection_file=str(selection_path)))
    assert [job.id for job in selected] == ["a", "c"]


def test_unknown_explicit_id_fails_fast():
    with pytest.raises(ValueError, match="unknown test IDs"):
        select_jobs(_jobs(), Selection(test_ids=["missing"]))
