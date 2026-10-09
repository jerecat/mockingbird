from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .io import read_json
from .models import Job
from .results import final_results


@dataclass
class Selection:
    failed_from: str | None = None
    test_ids: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    selection_file: str | None = None


def resolve_result_path(value: str | Path) -> Path:
    path = Path(value).resolve()
    if path.is_dir():
        path = path / "result.json"
    if not path.is_file():
        raise FileNotFoundError(f"result not found: {path}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def failed_ids(value: str | Path) -> set[str]:
    result_path = resolve_result_path(value)
    result = read_json(result_path)
    return {
        str(test["id"])
        for test in final_results(result)
        if str(test.get("status", "")).upper() == "FAIL"
    }


def read_selection_file(path: str | Path) -> list[str]:
    values: list[str] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        values.append(line)
    return values


def write_selection_file(path: str | Path, jobs: Iterable[Job]) -> None:
    lines = [
        "# One job ID per line. Delete or comment out lines you do not want to run.",
        "# Core treats these only as opaque job IDs.",
        "",
    ]
    lines.extend(job.id for job in jobs)
    Path(path).write_text("\n".join(lines) + "\n")


def select_jobs(jobs: list[Job], selection: Selection) -> tuple[list[Job], dict]:
    known = {job.id for job in jobs}
    if len(known) != len(jobs):
        raise ValueError("plan contains duplicate job IDs")

    selected_ids = set(known)
    metadata: dict = {
        "failed_from": None,
        "failed_from_run_id": None,
        "failed_from_sha256": None,
        "explicit_test_ids": list(selection.test_ids),
        "patterns": list(selection.patterns),
        "selection_file": selection.selection_file,
    }

    if selection.failed_from:
        result_path = resolve_result_path(selection.failed_from)
        prior_result = read_json(result_path)
        selected_ids &= {
            str(test["id"])
            for test in final_results(prior_result)
            if str(test.get("status", "")).upper() == "FAIL"
        }
        metadata["failed_from"] = str(result_path)
        metadata["failed_from_run_id"] = prior_result.get("run_id")
        metadata["failed_from_sha256"] = _sha256(result_path)

    explicit: set[str] = set()
    explicit_requested = False

    if selection.test_ids:
        explicit_requested = True
        unknown = set(selection.test_ids) - known
        if unknown:
            raise ValueError(f"unknown test IDs: {', '.join(sorted(unknown))}")
        explicit.update(selection.test_ids)

    for pattern in selection.patterns:
        explicit_requested = True
        matched = {job_id for job_id in known if fnmatch.fnmatchcase(job_id, pattern)}
        if not matched:
            raise ValueError(f"pattern matched no tests: {pattern!r}")
        explicit.update(matched)

    if selection.selection_file:
        explicit_requested = True
        from_file = read_selection_file(selection.selection_file)
        unknown = set(from_file) - known
        if unknown:
            raise ValueError(
                f"selection file contains unknown test IDs: {', '.join(sorted(unknown))}"
            )
        explicit.update(from_file)

    if explicit_requested:
        selected_ids &= explicit

    selected = [job for job in jobs if job.id in selected_ids]
    if not selected:
        raise ValueError("selection produced zero jobs")

    metadata["selected_count"] = len(selected)
    metadata["plan_count"] = len(jobs)
    metadata["selected_ids"] = [job.id for job in selected]
    return selected, metadata
