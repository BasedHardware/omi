"""Schema reconcile before every FinOps load. Incident #23289 (f16409f5) added
`annual_estimated_usd` and `annual_history_reason` to the code schema; the prod
`mercury_saas_daily` predated them, so the first post-deploy
`finops-unit-cost-job` run failed BigQuery 400 "Column annual_estimated_usd ...".
Synthetic API shapes only: no project, network or credentials. The contract:

  * a live table missing a SCHEMAS column gets it added as NULLABLE (one ALTER)
    and the load then proceeds;
  * columns are never dropped or retyped: an extra live column is left alone,
    and a type disagreement fails the run (that change needs a migration);
  * a table that already matches produces no DDL, and an absent table is still
    created whole by `ensure_table`.
"""

import importlib.util
import json
import pathlib
import types

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def loader(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    return load("load_bigquery")


# `bq show` reports legacy type names; the code schemas use the standard ones.
LEGACY_TYPES = {"INT64": "INTEGER", "FLOAT64": "FLOAT", "BOOL": "BOOLEAN"}


def make_show(fields):
    doc = {"schema": {"fields": [{"name": n, "type": LEGACY_TYPES.get(t, t), "mode": "NULLABLE"} for n, t in fields]}}
    return lambda: types.SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")


# The #23289 shape: the live mercury_saas_daily predates two code columns.
MISSING_SAAS = ("annual_estimated_usd", "annual_history_reason")


def old_mercury_saas(loader):
    return [(c, t) for c, t in loader.SCHEMAS["mercury_saas_daily"] if c not in MISSING_SAAS]


def test_missing_columns_added_as_nullable_alter(loader):
    altered = []
    added = loader.ensure_columns("mercury_saas_daily", show=make_show(old_mercury_saas(loader)), run=altered.append)
    assert added == list(MISSING_SAAS)
    assert len(altered) == 1
    sql = altered[0]
    assert sql.startswith("ALTER TABLE `based-hardware.omi_finops.mercury_saas_daily`")
    assert "ADD COLUMN IF NOT EXISTS annual_estimated_usd NUMERIC" in sql
    assert "ADD COLUMN IF NOT EXISTS annual_history_reason STRING" in sql
    assert "DROP" not in sql.upper()


def test_mercury_load_proceeds_after_the_reconcile(loader, monkeypatch, tmp_path):
    """The full loader path over a fake `bq`: the incident's stale table is
    reconciled in place before its load, and both tables load."""
    day = "2026-10-15"
    (tmp_path / "mercury_vendor_spend_daily.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "start": day,
                "end": day,
                "rows": [
                    {"date": day, "vendor": "vercel", "category": "saas", "amount_usd": "30", "transaction_count": 1},
                    {
                        "date": day,
                        "vendor": "unmapped",
                        "category": "unmapped",
                        "amount_usd": "0",
                        "transaction_count": 0,
                    },
                ],
            }
        )
    )
    tables = {
        # vendor_spend_daily is current; mercury_saas_daily predates #23289's columns.
        "mercury_vendor_spend_daily": list(loader.SCHEMAS["mercury_vendor_spend_daily"]),
        "mercury_saas_daily": old_mercury_saas(loader),
    }
    cmds = []

    def fake_run(args, input=None, capture_output=True, text=True, timeout=None):
        cmd = args[2]  # after "bq", "--project_id=..."
        if cmd == "show":
            fields = tables.get(args[-1].split(".")[-1])
            if fields is None:
                return types.SimpleNamespace(returncode=1, stdout="", stderr="Not found")
            doc = {"schema": {"fields": [{"name": n, "type": LEGACY_TYPES.get(t, t)} for n, t in fields]}}
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")
        cmds.append((cmd, input))
        if cmd == "query" and "--format=json" in args:
            return types.SimpleNamespace(returncode=0, stdout="[]", stderr="")  # the history read sees no prior rows
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(loader.subprocess, "run", fake_run)
    mercury = load("load_mercury")
    result = mercury.load(
        tmp_path, "run-1", "2026-10-16T00:00:00Z", loader.ensure_table, loader.load_replace, loader.bq
    )
    assert set(result) == {"mercury_vendor_spend_daily", "mercury_saas_daily", "mercury_infra_non_gcp_daily"}
    alters = [i for c, i in cmds if c == "query" and i and "ADD COLUMN IF NOT EXISTS" in i]
    assert len(alters) == 1
    assert "annual_estimated_usd NUMERIC" in alters[0]
    inserts = [
        i for c, i in cmds if c == "query" and i and "INSERT INTO `based-hardware.omi_finops.mercury_saas_daily`" in i
    ]
    assert len(inserts) == 1
    # The reconcile strictly precedes the load it unblocks.
    assert cmds.index(("query", alters[0])) < cmds.index(("query", inserts[0]))
    assert not any("DROP" in (i or "").upper() for c, i in cmds)


def test_type_mismatch_fails_closed_with_migration_message(loader):
    retyped = [(c, "STRING" if c == "amount_usd" else t) for c, t in loader.SCHEMAS["mercury_saas_daily"]]
    altered = []
    with pytest.raises(SystemExit, match="migration"):
        loader.ensure_columns("mercury_saas_daily", show=make_show(retyped), run=altered.append)
    assert altered == []  # nothing was added or touched


def test_current_table_with_extra_live_column_produces_no_ddl(loader):
    altered = []
    extra = [(c, t) for c, t in loader.SCHEMAS["unit_cost_daily"]] + [("legacy_col", "STRING")]
    assert loader.ensure_columns("unit_cost_daily", show=make_show(extra), run=altered.append) == []
    assert altered == []  # extra live columns are never dropped; legacy type names match


def test_absent_table_is_still_created_whole(loader, monkeypatch):
    created = []

    def fake_run(args, input=None, capture_output=True, text=True, timeout=None):
        cmd = args[2]
        if cmd == "show":
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Not found")
        created.append((cmd, args))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(loader.subprocess, "run", fake_run)
    loader.ensure_table("mercury_saas_daily")
    assert [c for c, _ in created] == ["mk"]
    schema = created[0][1][-1]
    assert "annual_estimated_usd:NUMERIC" in schema  # born with the current code schema
