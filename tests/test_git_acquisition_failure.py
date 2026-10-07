"""A failed first acquisition is never published as a reusable checkout."""
import subprocess
from pathlib import Path

import pytest

from mockingbird.sources import git


def origin(tmp_path):
    path = tmp_path / 'origin'; path.mkdir()
    def command(*args):
        return subprocess.run(['git', *args], cwd=path, capture_output=True, text=True, check=True)
    command('init', '-b', 'main')
    (path/'source.txt').write_text('original')
    command('add', 'source.txt')
    command('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
    return path


def test_invalid_revision_fails_repeatedly_then_corrected_revision_succeeds(tmp_path):
    source = origin(tmp_path); destination = tmp_path/'checkout'
    provider = git.Provider()
    for _ in range(2):
        with pytest.raises(RuntimeError, match='cannot resolve git revision'):
            provider.materialize({'url': str(source), 'revision': 'missing'}, destination)
        assert not destination.exists()
    result = provider.materialize({'url': str(source), 'revision': 'main'}, destination)
    assert result['materialization'] == 'created'
    assert (destination/'source.txt').read_text() == 'original'
    (destination/'source.txt').write_text('user edit')
    result = provider.materialize({'url': 'unused', 'revision': 'missing'}, destination)
    assert result['materialization'] == 'reused'
    assert (destination/'source.txt').read_text() == 'user edit'


def test_failed_checkout_preserves_original_empty_destination(tmp_path, monkeypatch):
    source = origin(tmp_path); destination = tmp_path/'checkout'; destination.mkdir()
    original = git._run
    def fail_checkout(args, **kwargs):
        if args[:2] == ['git', 'checkout']:
            raise subprocess.CalledProcessError(1, args)
        return original(args, **kwargs)
    monkeypatch.setattr(git, '_run', fail_checkout)
    with pytest.raises(subprocess.CalledProcessError):
        git.Provider().materialize({'url': str(source)}, destination)
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert not list(tmp_path.glob('.checkout-clone-*'))
    monkeypatch.setattr(git, '_run', original)
    assert git.Provider().materialize({'url': str(source)}, destination)['materialization'] == 'created'


def test_files_created_in_destination_during_clone_are_not_replaced(tmp_path, monkeypatch):
    source = origin(tmp_path); destination = tmp_path/'checkout'
    original = git._run
    def user_created_files(args, **kwargs):
        result = original(args, **kwargs)
        if args[:2] == ['git', 'checkout']:
            destination.mkdir()
            (destination/'keep.txt').write_text('user data')
        return result
    monkeypatch.setattr(git, '_run', user_created_files)
    with pytest.raises(OSError):
        git.Provider().materialize({'url': str(source)}, destination)
    assert (destination/'keep.txt').read_text() == 'user data'
    assert not (destination/'.git').exists()
