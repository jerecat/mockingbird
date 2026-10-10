import json
import pytest
from mockingbird import report


def fixture_runs(tmp_path, monkeypatch):
    root = tmp_path / 'runs'
    root.mkdir()
    monkeypatch.setattr(report, 'run_root_path', lambda _: root)
    for number, ids in [(1, ['a', 'b']), (2, ['a', 'c']), (3, ['a'])]:
        rid = f'run{number}'
        p = root / rid
        p.mkdir()
        def write(name, data):
            (p / name).write_text(json.dumps(data))
        write('run.json', dict(run_id=rid, plan='smoke', started_at=f'2026-10-0{number}T12:00:00+00:00', status='EXECUTED', selection={'selected_ids': ids}, jobs={i: {} for i in ids}))
        write('plan.json', dict(plan='smoke', jobs=[dict(id=i, payload={'command': ['echo', i]}) for i in ids]))
        if number != 3:
            write('result.json', dict(run_id=rid, plan='smoke', generated_at='now', jobs={i: dict(state='COMPLETE', result=dict(id=i, status='PASS', artifacts=['/tmp/</script><script>alert(1)</script>'])) for i in ids}))
    return root


def test_union_missing_result_and_read_only(tmp_path, monkeypatch):
    root = fixture_runs(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in root.rglob('*.json')}
    data = report.load_report({'plan': 'smoke'})
    assert data['ids'] == ['a', 'b', 'c']
    assert 'b' not in data['runs'][1]['tests']
    assert data['runs'][2]['tests']['a']['status'] == 'UNCOLLECTED'
    path, runs, jobs = report.generate_report({'plan': 'smoke'}, tmp_path / 'out.html', exclude=['run1'])
    html = path.read_text()
    assert (runs, jobs) == (2, 2)
    assert 'run1' not in html
    assert '</script><script>alert(1)' not in html
    assert before == {p: p.read_bytes() for p in root.rglob('*.json')}


def test_selection(tmp_path, monkeypatch):
    fixture_runs(tmp_path, monkeypatch)
    def ids(**kwargs):
        return [r['id'] for r in report.load_report({'plan': 'smoke'}, **kwargs)['runs']]
    assert ids(exclude=['run3'], last=1) == ['run2']
    assert ids(runs=['run1', 'run2'], since='2026-10-02', until='2026-10-02') == ['run2']
    for kw in [dict(last=0), dict(runs=['unknown']), dict(since='bad'), dict(since='2026-10-04', until='2026-10-01'), dict(exclude=['run1','run2','run3'])]:
        with pytest.raises(ValueError): ids(**kw)


@pytest.mark.parametrize('field,value', [('run_id','wrong'), ('plan','wrong'), ('jobs', {})])
def test_mismatch(tmp_path, monkeypatch, field, value):
    root = fixture_runs(tmp_path, monkeypatch)
    p = root / 'run1/result.json'
    d = json.loads(p.read_text()); d[field] = value; p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='mismatch'):
        report.load_report({'plan': 'smoke'})


def test_refresh_and_collection_states(tmp_path, monkeypatch):
    root = fixture_runs(tmp_path, monkeypatch)
    p = root / 'run1/result.json'
    d = json.loads(p.read_text()); d['jobs']['a']={'state':'ERROR','reason':'parser failed'}; d['jobs']['b']={'state':'PENDING'};p.write_text(json.dumps(d))
    assert report.load_report({'plan':'smoke'})['runs'][0]['tests']['a']['status']=='COLLECTION_ERROR'
    d['jobs']['a']={'state':'COMPLETE','result':{'id':'a','status':'ERROR'}};p.write_text(json.dumps(d))
    assert report.load_report({'plan':'smoke'})['runs'][0]['tests']['a']['status']=='ERROR'
    with pytest.raises(ValueError): report.generate_report({'plan':'smoke'}, root/'bad.html')
