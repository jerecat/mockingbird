from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def write_json(path: Path, value: Any) -> None:
    """Replace one complete JSON snapshot atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


@contextmanager
def file_lock(path: Path, *, shared=False, blocking=False, message="operation is already running"):
    """Lock an existing plan directory; process exit releases the lock."""
    with path.open("a") as stream:
        mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        try:
            fcntl.flock(stream, mode | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise RuntimeError(message) from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def collection_lock(run_path: Path):
    """A second collect must not repeat work while the first owns this run."""
    with (run_path / ".collect.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("collection is already running for this run") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
