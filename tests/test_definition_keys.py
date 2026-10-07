"""Misspelled top-level contracts must not silently disappear."""
import json
import sys

import pytest

from mockingbird.context import load_definition, prepare


def valid(tmp_path):
    return {'workspace': str(tmp_path/'work'),
            'execution': {'command': [sys.executable, '-c', 'pass'], 'timeout_s': 2, 'jobs': ['a']},
            'scheduler': {'capacity_provider': 'fixed'}}


@pytest.mark.parametrize('key', ['setpu', 'schedular', 'workspce', 'unexpected', '_invocation_dir'])
def test_load_rejects_unknown_or_reserved_root_keys(tmp_path, key):
    path = tmp_path/'jobs.yaml'; data = valid(tmp_path); data[key] = {}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unknown definition field') as error:
        load_definition(path)
    assert key in str(error.value)
    if key == 'setpu': assert "did you mean 'setup'" in str(error.value)
    assert not (tmp_path/'work').exists()


def test_prepare_also_validates_programmatic_definitions(tmp_path):
    data = valid(tmp_path)
    data.update(_definition_path=str(tmp_path/'jobs.yaml'), _invocation_dir=str(tmp_path), setpu={})
    with pytest.raises(ValueError, match='setpu'): prepare(data)
    assert not (tmp_path/'work').exists()


def test_adapter_config_remains_an_extension_namespace(tmp_path):
    data = valid(tmp_path)
    data['execution'] = {'adapter': 'demo_linux', 'config': {'project_owned_key': 'kept'}}
    path = tmp_path/'jobs.yaml'; path.write_text(json.dumps(data))
    assert prepare(load_definition(path))['execution']['config']['project_owned_key'] == 'kept'


@pytest.mark.parametrize('text', ['[]', 'false', '0'])
def test_falsey_non_mapping_root_is_rejected(tmp_path, text):
    path = tmp_path/'jobs.yaml'; path.write_text(text)
    with pytest.raises(ValueError, match='root must be a mapping'): load_definition(path)
