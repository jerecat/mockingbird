import io
import subprocess
from threading import Event

import pytest

from mockingbird import cli
from mockingbird.sources.git import Provider


def test_redirected_progress_starts_immediately_and_stops_on_interrupt(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(cli.sys, 'stdout', stream)
    with pytest.raises(KeyboardInterrupt):
        with cli._source_check():
            assert stream.getvalue() == 'Checking sources...\n'
            raise KeyboardInterrupt
    assert '\r' not in stream.getvalue()


def test_tty_animation_stops_on_error(monkeypatch):
    updated = Event()

    class Terminal(io.StringIO):
        def isatty(self):
            return True

        def write(self, value):
            result = super().write(value)
            if '\r' in value:
                updated.set()
            return result

    stream = Terminal()
    monkeypatch.setattr(cli.sys, 'stdout', stream)
    monkeypatch.setattr(cli, 'SOURCE_PROGRESS_INTERVAL_S', 0.001)
    with pytest.raises(RuntimeError):
        with cli._source_check():
            assert updated.wait(2)
            raise RuntimeError('observation failed')
    saved = stream.getvalue()
    assert '\rChecking sources' in saved
    assert saved.endswith('\n')
    # The context joined the worker; no output can arrive after this boundary.
    assert stream.getvalue() == saved


def test_timeout_records_unknown_and_preserves_head(monkeypatch, tmp_path):
    def inspect(args, **kwargs):
        if 'rev-parse' in args:
            return subprocess.CompletedProcess(args, 0, stdout='abc\n')
        raise subprocess.TimeoutExpired(args, kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', inspect)
    observation = Provider().observe({'path': tmp_path, 'resolved_revision': 'abc'})
    assert observation['current_commit'] == 'abc'
    assert observation['tracked_dirty'] is None
    assert 'TimeoutExpired' in observation['error']


@pytest.mark.parametrize('dirty', [True, False, None])
def test_save_tracked_observations_warn_about_untracked(dirty):
    warnings = Provider().export_source({'name': 'dut'}, {},
                                       {'current_commit': 'abc', 'tracked_dirty': dirty})
    assert any('untracked files were not checked' in warning for warning in warnings)
    if dirty is True:
        assert any('was dirty' in warning for warning in warnings)
    if dirty is None:
        assert any('unknown' in warning for warning in warnings)
