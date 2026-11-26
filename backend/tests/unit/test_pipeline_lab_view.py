"""``view PATH``: one entry point that picks the scenario page or the day-replay inspector from the path."""

import json

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.inspector import view as viewer


def _touch(path, text='{}'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.mark.parametrize(
    'files',
    [
        ['verdict.json', 'run.json', 'a/result.json'],  # scenario run --keep DIR
        ['a/result.json'],  # scenario folders only
        ['result.json'],  # one scenario's directory
        ['compare.json', 'base/a/result.json', 'head/a/result.json'],  # scenario compare
    ],
)
def test_scenario_directories_open_the_scenario_page(tmp_path, files):
    for rel in files:
        _touch(tmp_path / rel)
    assert viewer.detect(str(tmp_path)) == viewer.Target('scenario', tmp_path.resolve())


def test_store_root_and_day_run_open_the_day_inspector(tmp_path):
    root = tmp_path / 'store'
    _touch(root / 'runs' / 'run-1' / 'run.json')
    assert viewer.detect(str(root)) == viewer.Target('day', root.resolve())
    assert viewer.detect(str(root / 'runs' / 'run-1')) == viewer.Target('day', root.resolve(), 'run-1')


def test_neither_kind_exits_2_naming_what_was_looked_for(tmp_path, capsys):
    (tmp_path / 'empty').mkdir()
    for path in (tmp_path / 'empty', tmp_path / 'missing'):
        code = cli.main(['view', str(path)])
        err = capsys.readouterr().err
        assert code == 2 and 'verdict.json' in err and 'runs/' in err


def test_view_dispatches_to_each_server(tmp_path, monkeypatch):
    from testing.pipeline_lab.inspector import scenario_view, server

    calls = []
    monkeypatch.setattr(scenario_view, 'serve', lambda path, port=0: calls.append(('scenario', path, port)) or 0)
    monkeypatch.setattr(server, 'main', lambda argv: calls.append(('day', argv)) or 0)
    _touch(tmp_path / 'scn' / 'verdict.json', json.dumps({'scenarios': []}))
    _touch(tmp_path / 'store' / 'runs' / 'r1' / 'run.json')
    assert cli.main(['view', str(tmp_path / 'scn'), '--port', '9']) == 0
    assert cli.main(['view', str(tmp_path / 'store' / 'runs' / 'r1')]) == 0
    assert calls[0] == ('scenario', str((tmp_path / 'scn').resolve()), 9)
    assert calls[1] == ('day', ['--root', str((tmp_path / 'store').resolve()), '--port', '0'])
