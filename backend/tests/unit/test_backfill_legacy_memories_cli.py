"""Safety contract for the explicit single-user historical repair CLI."""

import os
from types import SimpleNamespace

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from scripts import backfill_legacy_memories as cli


def test_single_uid_repair_is_dry_run_by_default(monkeypatch, capsys):
    observed: dict[str, object] = {}

    def _backfill(uid: str, **kwargs):
        observed.update(uid=uid, **kwargs)
        return SimpleNamespace(dry_run=True, completed=False, errors=[])

    monkeypatch.setattr(cli, "backfill_user", _backfill)

    assert cli.main(["--uid", "uid-explicit"]) == 0
    assert observed["uid"] == "uid-explicit"
    assert observed["dry_run"] is True
    assert '"dry_run": true' in capsys.readouterr().out


def test_single_uid_repair_requires_explicit_apply_for_writes(monkeypatch):
    observed: dict[str, object] = {}

    def _backfill(uid: str, **kwargs):
        observed.update(uid=uid, **kwargs)
        return SimpleNamespace(dry_run=False, completed=True, errors=[])

    monkeypatch.setattr(cli, "backfill_user", _backfill)

    assert cli.main(["--uid", "uid-explicit", "--apply"]) == 0
    assert observed["dry_run"] is False
