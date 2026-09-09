"""Unit tests for the finops unit-cost allocator's pure functions.

These cover the arithmetic that decides how many dollars land on a user, not the pulls.
They are deliberately hermetic: no GCP, no Firestore, no network.
"""

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "finops_assemble",
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops" / "assemble_unit_cost.py",
)
alloc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(alloc)


# ---------------------------------------------------------------- fnum / is_one_time
@pytest.mark.parametrize(
    "value,expected",
    [("1.5", 1.5), ("", 0.0), (None, 0.0), ("not a number", 0.0), (3, 3.0), ("-2", -2.0)],
)
def test_fnum_never_raises(value, expected):
    assert alloc.fnum(value) == expected


def test_one_time_components_are_recognised_by_prefix():
    assert alloc.is_one_time("one_time_storage_lifecycle")
    assert not alloc.is_one_time("storage_audio")
    assert not alloc.is_one_time("firestore_reads")


# ---------------------------------------------------------------- cohort classification
@pytest.mark.parametrize(
    "desktop,mobile,web,expected",
    [
        ("2026-09-03", "2026-09-02", "", "dual"),
        ("2026-09-03", "", "", "desktop_only"),
        ("", "2026-09-03", "", "mobile_only"),
        ("", "", "2026-09-03", "web_only"),
        ("2026-08-20", "2026-08-21", "2026-08-22", "inactive_7d"),
        ("", "", "", "inactive_7d"),
        # boundary: the window start itself counts as inside the window
        ("2026-09-01", "", "", "desktop_only"),
        ("2026-08-31", "", "", "inactive_7d"),
        # desktop+web without mobile is still desktop_only: web never promotes to dual
        ("2026-09-02", "", "2026-09-02", "desktop_only"),
    ],
)
def test_classify_cohort(desktop, mobile, web, expected):
    assert alloc.classify_cohort(desktop, mobile, web, "2026-09-01") == expected


# ---------------------------------------------------------------- day pools
COMPONENTS = {
    "firestore_reads": 400.0,
    "cloud_run_other": 100.0,
    "asr_gpu_fleet": 150.0,
    "storage_audio": 50.0,
    "listen_pipeline_compute": 25.0,
    "vertex_paygo": 40.0,
    "embeddings": 30.0,
    "cloud_run_desktop_backend": 20.0,
    "vertex_pt_reservation": 300.0,
    "bigquery": 9.0,
    "one_time_storage_lifecycle": 13818.0,
}


def test_day_pools_group_components_as_documented():
    p = alloc.day_pools(COMPONENTS, residual_openai=30.0, residual_anthropic=5.0, vad_sent_hours=1000.0)
    assert p["shared_gcp"] == 500.0  # firestore_reads + cloud_run_other
    assert p["audio_pipeline_gcp"] == 225.0  # asr + audio bucket + listen/pusher pools
    assert p["desktop_pools"] == 50.0  # embeddings + desktop-backend
    assert p["vertex_paygo"] == 40.0
    assert p["vertex_pt_fixed"] == 300.0
    assert p["llm_direct_residual"] == 35.0


def test_day_pools_exclude_one_time_and_overhead():
    """A one-off charge must never reach a pool, and BigQuery overhead is not shared cost."""
    p = alloc.day_pools(COMPONENTS, 0.0, 0.0, 0.0)
    assert all(13818.0 not in (v,) for v in p.values())
    assert p["shared_gcp"] == 500.0  # bigquery ($9) is not in SHARED


def test_day_pools_one_time_is_not_silently_swallowed_by_shared():
    with_one_time = alloc.day_pools(COMPONENTS, 0.0, 0.0, 0.0)
    without = alloc.day_pools({k: v for k, v in COMPONENTS.items() if not alloc.is_one_time(k)}, 0.0, 0.0, 0.0)
    assert with_one_time == without


def test_stt_pool_is_hours_times_rate_with_a_high_case():
    p = alloc.day_pools({}, 0.0, 0.0, vad_sent_hours=1000.0, rate_per_min=0.0043)
    assert p["stt_vendor_low"] == pytest.approx(1000 * 60 * 0.0043)
    assert p["stt_vendor_high"] == pytest.approx(p["stt_vendor_low"] * alloc.STT_VENDOR_HIGH_MULTIPLIER)


# ---------------------------------------------------------------- per-user allocation
POOLS = {
    "shared_gcp": 1000.0,
    "audio_pipeline_gcp": 200.0,
    "vertex_paygo": 40.0,
    "desktop_pools": 50.0,
    "llm_direct_residual": 30.0,
    "vertex_pt_fixed": 300.0,
    "stt_vendor_low": 100.0,
    "stt_vendor_high": 180.0,
}
TOTALS = {"openai": 100.0, "gemini": 20.0, "desktop": 10.0, "tx_sec": 3600.0, "attempts": 1000}


def _fact(**kw):
    base = {"llm_openai": 0.0, "llm_gemini": 0.0, "fc_desktop": 0.0, "tx_sec": 0.0, "attempts": 0}
    base.update(kw)
    return base


def test_allocate_user_day_uses_each_driver():
    r = alloc.allocate_user_day(
        _fact(llm_openai=25.0, llm_gemini=5.0, fc_desktop=2.0, tx_sec=900.0, attempts=250), POOLS, TOTALS, n_users=10
    )
    assert r["llm_openai_measured"] == 25.0  # measured, passed through
    assert r["llm_direct_residual"] == pytest.approx(30.0 * 0.25)
    assert r["vertex_paygo"] == pytest.approx(40.0 * 0.25)
    assert r["audio_pipeline_gcp"] == pytest.approx(200.0 * 0.25)
    assert r["desktop_pools"] == pytest.approx(50.0 * 0.20)
    assert r["shared_headcount"] == pytest.approx(100.0)  # 1000 / 10 users
    assert r["vertex_pt_fixed"] == pytest.approx(300.0 * 0.25)
    assert r["stt_vendor_low"] == pytest.approx(100.0 * 0.25)


def test_gemini_list_price_is_a_memo_not_a_cost():
    """Gemini is served by the PT reservation; its ledger list price must not enter any total."""
    r = alloc.allocate_user_day(_fact(llm_gemini=5.0), POOLS, TOTALS, n_users=10)
    assert r["llm_gemini_list_memo"] == 5.0
    assert r["variable_total"] == pytest.approx(r["shared_headcount"] + r["vertex_paygo"])
    assert r["llm_gemini_list_memo"] not in (r["variable_total"], r["fully_loaded"], r["gross_total"])


def test_aggregate_components_compose_as_documented():
    r = alloc.allocate_user_day(
        _fact(llm_openai=25.0, llm_gemini=5.0, fc_desktop=2.0, tx_sec=900.0, attempts=250), POOLS, TOTALS, n_users=10
    )
    assert r["variable_total"] == pytest.approx(
        r["llm_openai_measured"]
        + r["llm_direct_residual"]
        + r["vertex_paygo"]
        + r["audio_pipeline_gcp"]
        + r["desktop_pools"]
        + r["shared_headcount"]
    )
    assert r["fully_loaded"] == pytest.approx(r["variable_total"] + r["vertex_pt_fixed"])
    assert r["gross_total"] == pytest.approx(r["fully_loaded"] + r["stt_vendor_low"])
    assert r["variable_total_activity"] == pytest.approx(
        r["variable_total"] - r["shared_headcount"] + r["shared_activity"]
    )


def test_activity_weighting_is_half_headcount_quarter_attempts_quarter_transcription():
    r = alloc.allocate_user_day(_fact(tx_sec=1800.0, attempts=500), POOLS, TOTALS, n_users=10)
    assert r["shared_activity"] == pytest.approx(1000.0 * (0.5 / 10 + 0.25 * 0.5 + 0.25 * 0.5))


def test_zero_drivers_never_divide_by_zero():
    empty = {"openai": 0.0, "gemini": 0.0, "desktop": 0.0, "tx_sec": 0.0, "attempts": 0}
    r = alloc.allocate_user_day(_fact(), POOLS, empty, n_users=0)
    assert r["shared_headcount"] == 0.0
    assert r["variable_total"] == 0.0
    assert r["gross_total"] == 0.0


def test_allocation_is_conservative_across_users():
    """Every pool must be fully spent across the day's users and never over-spent."""
    facts = [
        _fact(llm_openai=60.0, llm_gemini=12.0, fc_desktop=6.0, tx_sec=2000.0, attempts=600),
        _fact(llm_openai=40.0, llm_gemini=8.0, fc_desktop=4.0, tx_sec=1600.0, attempts=400),
    ]
    rows = [alloc.allocate_user_day(f, POOLS, TOTALS, n_users=len(facts)) for f in facts]
    for component, pool_key in (
        ("audio_pipeline_gcp", "audio_pipeline_gcp"),
        ("vertex_paygo", "vertex_paygo"),
        ("desktop_pools", "desktop_pools"),
        ("llm_direct_residual", "llm_direct_residual"),
        ("vertex_pt_fixed", "vertex_pt_fixed"),
        ("stt_vendor_low", "stt_vendor_low"),
    ):
        assert sum(r[component] for r in rows) == pytest.approx(POOLS[pool_key])
    assert sum(r["shared_headcount"] for r in rows) == pytest.approx(POOLS["shared_gcp"])
    assert sum(r["shared_activity"] for r in rows) == pytest.approx(POOLS["shared_gcp"])


# ---------------------------------------------------------------- reconciliation
def test_reconcile_day_closes_on_a_complete_allocation():
    facts = [_fact(llm_openai=100.0, llm_gemini=20.0, fc_desktop=10.0, tx_sec=3600.0, attempts=1000)]
    rows = [alloc.allocate_user_day(f, POOLS, TOTALS, n_users=1) for f in facts]
    allocated = {c: sum(r[c] for r in rows) for c in alloc.COMPS}
    recon = alloc.reconcile_day(
        "2026-09-07",
        POOLS,
        allocated,
        COMPONENTS,
        gcp_export_net=sum(COMPONENTS.values()),
        openai_invoice=130.0,
        anthropic_invoice=0.0,
        settled=True,
    )
    by_pool = {r["pool"]: r for r in recon}
    for pool in (
        "shared_gcp",
        "audio_pipeline_gcp",
        "vertex_paygo",
        "desktop_pools",
        "vertex_pt_fixed",
        "stt_vendor_low",
        "gcp_total_export",
    ):
        assert abs(by_pool[pool]["delta_pct"]) < 0.5, pool


def test_reconcile_day_reports_one_time_separately_and_flags_a_lossy_classifier():
    recon = alloc.reconcile_day(
        "2026-09-07",
        POOLS,
        {},
        COMPONENTS,
        gcp_export_net=sum(COMPONENTS.values()) + 500.0,
        openai_invoice=0.0,
        anthropic_invoice=0.0,
        settled=False,
    )
    by_pool = {r["pool"]: r for r in recon}
    assert by_pool["one_time"]["pool_usd"] == 13818.0
    assert by_pool["one_time"]["allocated_usd"] == 13818.0
    assert abs(by_pool["gcp_total_export"]["delta_pct"]) > 0.5  # 500 unclassified dollars must show
    assert by_pool["one_time"]["inputs_settled"] is False


def test_every_component_has_a_declared_method():
    assert set(alloc.COMPS) == set(alloc.METHOD)
    assert set(alloc.METHOD.values()) <= {"measured", "driver-allocated", "headcount", "fixed", "modelled"}


# ---------------------------------------------------------------- roll-up
def test_rollup_divides_totals_by_the_window_length():
    rows = []
    for date in ("2026-09-01", "2026-09-02"):
        for uid in ("aaaa", "bbbb"):
            r = {"date": date, "uid_hash": uid, "cohort": "dual", "plan": "plus", "attempts": 10, "tx_sec": 3600.0}
            r.update({c: 1.0 for c in alloc.COMPS})
            rows.append(r)
    out = alloc.rollup(rows, lambda r: r["plan"], n_days=2)
    assert len(out) == 1
    assert out[0]["user_days"] == 4
    assert out[0]["mean_users_per_day"] == 2.0
    assert out[0]["variable_total_per_day"] == 2.0  # 4 user-days x $1 over 2 days
    assert out[0]["variable_total_per_user_day"] == 1.0


def test_long_rows_count_a_dual_user_in_both_platform_unions():
    rows = []
    for cohort in ("dual", "mobile_only"):
        r = {"date": "2026-09-01", "uid_hash": cohort, "cohort": cohort, "plan": "basic", "attempts": 0, "tx_sec": 0.0}
        r.update({c: 1.0 for c in alloc.COMPS})
        rows.append(r)

    def union(r):
        segs = [s for s, members in alloc.PLATFORM_UNION_MEMBERS.items() if r["cohort"] in members]
        return segs or ["other_union"]

    out = alloc.long_rows(rows, lambda r: r["date"], [("platform_union", union), ("total", lambda r: "all")])
    seg = {(r["segment_type"], r["segment"], r["component"]): r for r in out}
    assert seg[("platform_union", "desktop_incl_dual", "variable_total")]["users"] == 1
    assert seg[("platform_union", "mobile_incl_dual", "variable_total")]["users"] == 2
    assert seg[("total", "all", "variable_total")]["usd"] == 2.0
    assert seg[("total", "all", "variable_total")]["usd_per_user_day"] == 1.0


def test_long_rows_carry_the_method_for_every_component():
    r = {"date": "2026-09-01", "uid_hash": "aaaa", "cohort": "dual", "plan": "plus", "attempts": 0, "tx_sec": 0.0}
    r.update({c: 1.0 for c in alloc.COMPS})
    out = alloc.long_rows([r], lambda x: x["date"], [("total", lambda x: "all")])
    assert {x["component"] for x in out} == set(alloc.COMPS)
    assert all(x["method"] == alloc.METHOD[x["component"]] for x in out)


# ---------------------------------------------------------------- cohort window
def test_cohort_window_is_a_trailing_window_ending_on_the_usage_day():
    """The same usage day must get the same cohort window alone or inside a backfill."""
    assert alloc.cohort_window_start_for("2026-09-07", 7) == "2026-09-01"
    assert alloc.cohort_window_start_for("2026-09-01", 7) == "2026-08-26"
    assert alloc.cohort_window_start_for("2026-09-07", 1) == "2026-09-07"


def test_cohort_window_can_be_pinned_to_reproduce_an_older_report():
    assert alloc.cohort_window_start_for("2026-09-07", 7, fixed="2026-08-31") == "2026-08-31"
    assert alloc.cohort_window_start_for("2026-09-01", 7, fixed="2026-08-31") == "2026-08-31"
