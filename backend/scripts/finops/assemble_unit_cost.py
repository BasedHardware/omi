#!/usr/bin/env python3
"""Assemble Omi true user unit cost by platform cohort and plan from the raw pulls.

Inputs (the run's raw/ dir):
  gcp_components_daily.json, gcp_day_resource_top.json, gcp_day_service_sku.json, gcp_recon.json
  openai_cost_daily.json, anthropic_cost_daily.json
  ledger_user_daily.csv, ledger_agg_daily.csv
  users_active_30d.csv, stt_usage_daily.csv, posthog_dau_daily.csv, prom_stt_7d.json

Method: every dollar lands on a (day, uid) row via one of these classes, then rolls up.
  measured          - ledger LLM cost priced per attempt, joined to uid
  driver-allocated  - pool allocated by a measured per-uid driver (transcription seconds,
                      ledger OpenAI/Gemini share, desktop-feature share)
  headcount         - pool split evenly across that day's cost-active users (Firestore reads etc.)
  fixed             - Vertex PT reservation; reported separately, only in the fully-loaded view
  modelled          - no invoice feed exists (STT vendor volume x a placeholder rate; Gemini list memo)
  one_time          - dated one-off charges (see one_time_events.json). Reported at the day level,
                      NEVER allocated to a user and never part of a run rate.
No raw uids anywhere: inputs are already sha256[:16] hashes.

Usage:
  assemble_unit_cost.py RAW OUT [START [END [COHORT_WINDOW_START]]] [--cohort-lookback-days N]
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import pathlib
import sys

STT_VENDOR_RATE_PER_MIN = 0.0043  # PLACEHOLDER (Deepgram Nova list). Modulate/Soniox contract rates pending.
STT_VENDOR_HIGH_MULTIPLIER = 1.8

SHARED = [
    "firestore_reads",
    "firestore_other",
    "cloud_run_other",
    "logging_monitoring",
    "network",
    "pubsub",
    "other_gcp",
    "storage_other",
    "gke_other_compute",
    "translate",
]
AUDIO = ["asr_gpu_fleet", "storage_audio", "listen_pipeline_compute"]
DESKTOP_POOLS = ["embeddings", "cloud_run_desktop_backend"]
EXCLUDED_FROM_VARIABLE = ["bigquery", "vertex_pt_reservation"]  # overhead / fixed

COMPS = [
    "llm_openai_measured",
    "llm_direct_residual",
    "vertex_paygo",
    "audio_pipeline_gcp",
    "desktop_pools",
    "shared_headcount",
    "shared_activity",
    "variable_total",
    "variable_total_activity",
    "vertex_pt_fixed",
    "fully_loaded",
    "llm_gemini_list_memo",
    "stt_vendor_low",
    "stt_vendor_high",
    "gross_total",
]

METHOD = {
    "llm_openai_measured": "measured",
    "llm_direct_residual": "driver-allocated",
    "vertex_paygo": "driver-allocated",
    "audio_pipeline_gcp": "driver-allocated",
    "desktop_pools": "driver-allocated",
    "shared_headcount": "headcount",
    "shared_activity": "driver-allocated",
    "vertex_pt_fixed": "fixed",
    "llm_gemini_list_memo": "modelled",
    "stt_vendor_low": "modelled",
    "stt_vendor_high": "modelled",
    # aggregates take the weakest method they contain
    "variable_total": "driver-allocated",
    "variable_total_activity": "driver-allocated",
    "fully_loaded": "driver-allocated",
    "gross_total": "modelled",
}


# ---------------------------------------------------------------- pure helpers (unit tested)
def fnum(x) -> float:
    try:
        return float(x or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def is_one_time(component: str) -> bool:
    return component.startswith("one_time")


def classify_cohort(last_desktop: str, last_mobile: str, last_web: str, window_start: str) -> str:
    """Platform cohort from the users snapshot's last_active_at_* dates.

    A user counts on a platform if they were last seen there on or after `window_start`.
    Dual users are their own segment: nothing pretends to split a dual user's cost.
    """
    d = (last_desktop or "") >= window_start
    m = (last_mobile or "") >= window_start
    w = (last_web or "") >= window_start
    if d and m:
        return "dual"
    if d:
        return "desktop_only"
    if m:
        return "mobile_only"
    if w:
        return "web_only"
    return "inactive_7d"


def day_pools(
    components: dict,
    residual_openai: float,
    residual_anthropic: float,
    vad_sent_hours: float,
    rate_per_min: float = STT_VENDOR_RATE_PER_MIN,
) -> dict:
    """The allocatable pools for one usage day. One-time components are never in a pool."""
    c = {k: v for k, v in components.items() if not is_one_time(k)}
    return {
        "shared_gcp": sum(c.get(k, 0.0) for k in SHARED),
        "audio_pipeline_gcp": sum(c.get(k, 0.0) for k in AUDIO),
        "vertex_paygo": c.get("vertex_paygo", 0.0),
        "desktop_pools": sum(c.get(k, 0.0) for k in DESKTOP_POOLS),
        "llm_direct_residual": residual_openai + residual_anthropic,
        "vertex_pt_fixed": c.get("vertex_pt_reservation", 0.0),
        "stt_vendor_low": vad_sent_hours * 60 * rate_per_min,
        "stt_vendor_high": vad_sent_hours * 60 * rate_per_min * STT_VENDOR_HIGH_MULTIPLIER,
    }


def allocate_user_day(f: dict, pools: dict, totals: dict, n_users: int) -> dict:
    """Split the day's pools onto one user by that user's measured drivers.

    `f` carries the user's measured facts (llm_openai, llm_gemini, fc_desktop, tx_sec, attempts);
    `totals` the same quantities summed over the day; `n_users` the day's cost-active headcount.
    """
    tot_oai, tot_gem = totals["openai"], totals["gemini"]
    tot_desk, tot_tx, tot_att = totals["desktop"], totals["tx_sec"], totals["attempts"]
    oai_share = f["llm_openai"] / tot_oai if tot_oai else 0
    gem_share = f["llm_gemini"] / tot_gem if tot_gem else 0
    desk_share = f["fc_desktop"] / tot_desk if tot_desk else 0
    tx_share = f["tx_sec"] / tot_tx if tot_tx else 0
    att_share = f["attempts"] / tot_att if tot_att else 0
    r = {
        "llm_openai_measured": f["llm_openai"],
        "llm_gemini_list_memo": f["llm_gemini"],  # NOT added to totals: served by the PT reservation
        "llm_direct_residual": pools["llm_direct_residual"] * oai_share,
        "vertex_paygo": pools["vertex_paygo"] * gem_share,
        "audio_pipeline_gcp": pools["audio_pipeline_gcp"] * tx_share,
        "desktop_pools": pools["desktop_pools"] * desk_share,
        "shared_headcount": pools["shared_gcp"] / n_users if n_users else 0.0,
        "shared_activity": (
            pools["shared_gcp"] * (0.5 / n_users + 0.25 * att_share + 0.25 * tx_share) if n_users else 0.0
        ),
        "vertex_pt_fixed": pools["vertex_pt_fixed"] * gem_share,
        "stt_vendor_low": pools["stt_vendor_low"] * tx_share,
        "stt_vendor_high": pools["stt_vendor_high"] * tx_share,
    }
    r["variable_total"] = sum(
        r[k]
        for k in (
            "llm_openai_measured",
            "llm_direct_residual",
            "vertex_paygo",
            "audio_pipeline_gcp",
            "desktop_pools",
            "shared_headcount",
        )
    )
    r["variable_total_activity"] = r["variable_total"] - r["shared_headcount"] + r["shared_activity"]
    r["fully_loaded"] = r["variable_total"] + r["vertex_pt_fixed"]
    r["gross_total"] = r["fully_loaded"] + r["stt_vendor_low"]
    return r


def reconcile_day(
    date: str,
    pools: dict,
    allocated: dict,
    components: dict,
    gcp_export_net: float,
    openai_invoice: float,
    anthropic_invoice: float,
    settled: bool,
) -> list:
    """One row per pool: what came off an invoice vs what landed on user-days."""
    one_time = sum(v for k, v in components.items() if is_one_time(k))
    rows = [
        (
            "shared_gcp",
            pools["shared_gcp"],
            allocated.get("shared_headcount", 0.0),
            "gcp_billing_export",
            "headcount split; activity-weighted alternative in shared_activity",
        ),
        (
            "audio_pipeline_gcp",
            pools["audio_pipeline_gcp"],
            allocated.get("audio_pipeline_gcp", 0.0),
            "gcp_billing_export",
            "driver = hourly_usage.transcription_seconds",
        ),
        (
            "vertex_paygo",
            pools["vertex_paygo"],
            allocated.get("vertex_paygo", 0.0),
            "gcp_billing_export",
            "driver = ledger gemini share",
        ),
        (
            "desktop_pools",
            pools["desktop_pools"],
            allocated.get("desktop_pools", 0.0),
            "gcp_billing_export",
            "driver = ledger desktop-feature share",
        ),
        (
            "vertex_pt_fixed",
            pools["vertex_pt_fixed"],
            allocated.get("vertex_pt_fixed", 0.0),
            "gcp_billing_export",
            "fixed reservation, fully-loaded view only",
        ),
        (
            "llm_openai",
            openai_invoice,
            allocated.get("llm_openai_measured", 0.0) + allocated.get("llm_direct_residual", 0.0) - anthropic_invoice,
            "openai_admin_api",
            "ledger measured + residual; anthropic rides the same residual pool",
        ),
        (
            "llm_anthropic",
            anthropic_invoice,
            anthropic_invoice,
            "anthropic_admin_api",
            "no ledger rows in this era; whole invoice is residual",
        ),
        (
            "llm_openai_ledger_coverage",
            openai_invoice,
            allocated.get("llm_openai_measured", 0.0),
            "openai_admin_api",
            "DIAGNOSTIC, not an allocation check: how much of the OpenAI invoice the "
            "per-attempt ledger explains. The remainder is llm_direct_residual.",
        ),
        (
            "stt_vendor_low",
            pools["stt_vendor_low"],
            allocated.get("stt_vendor_low", 0.0),
            "modelled",
            "vad-sent hours x $%.4f/min placeholder; no vendor invoice feed" % STT_VENDOR_RATE_PER_MIN,
        ),
        (
            "gcp_total_export",
            gcp_export_net,
            sum(components.values()),
            "gcp_billing_export",
            "classifier must lose nothing: components must equal the export",
        ),
        (
            "one_time",
            one_time,
            one_time,
            "gcp_billing_export",
            "dated one-off charges, excluded from every per-user pool",
        ),
    ]
    out = []
    for pool, pool_usd, alloc_usd, src, note in rows:
        delta = (alloc_usd - pool_usd) / pool_usd * 100 if pool_usd else 0.0
        out.append(
            {
                "date": date,
                "pool": pool,
                "pool_usd": round(pool_usd, 6),
                "allocated_usd": round(alloc_usd, 6),
                "delta_pct": round(delta, 6),
                "invoice_source": src,
                "note": note,
                "inputs_settled": settled,
            }
        )
    return out


# ---------------------------------------------------------------- loading
def load_components(raw: pathlib.Path):
    comp = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in json.load(open(raw / "gcp_components_daily.json")):
        comp[r["usage_day"]][r["component"]] += fnum(r["net"])
    # Reclassify listen/pusher GKE pools out of gke_other_compute into listen_pipeline_compute.
    listen_pool = collections.defaultdict(float)
    for r in json.load(open(raw / "gcp_day_resource_top.json")):
        labs = r.get("labels") or "[]"
        try:
            labs = json.loads(labs) if isinstance(labs, str) else labs
        except Exception:  # noqa: BLE001
            labs = []
        pool = next((l.get("value") for l in labs if l.get("key") == "goog-k8s-node-pool-name"), "")
        if pool.startswith(("backend-listen-pool", "pusher-pool")):
            listen_pool[r["usage_day"]] += fnum(r["net"])
    for d, v in listen_pool.items():
        v = min(v, comp[d]["gke_other_compute"])  # resource extract is top-3000 rows; never drive the residual negative
        comp[d]["gke_other_compute"] -= v
        comp[d]["listen_pipeline_compute"] += v
    dev_by_day = collections.defaultdict(float)
    for r in json.load(open(raw / "gcp_day_service_sku.json")):
        if r["project_id"] != "based-hardware":
            dev_by_day[r["usage_day"]] += fnum(r["net"])
    export_net, max_end = collections.defaultdict(float), {}
    p = raw / "gcp_recon.json"
    if p.exists():
        for r in json.load(open(p)):
            export_net[r["usage_day"]] += fnum(r["net"])
            max_end[r["usage_day"]] = r.get("max_usage_end_time")
    return comp, dev_by_day, export_net, max_end


def load_invoices(raw: pathlib.Path):
    openai_inv, openai_cache_writes = collections.defaultdict(float), collections.defaultdict(float)
    for b in json.load(open(raw / "openai_cost_daily.json"))["data"]:
        day = (dt.date.fromisoformat(b["end_time_iso"][:10]) - dt.timedelta(days=1)).isoformat()
        for x in b["results"]:
            openai_inv[day] += fnum(x["amount"]["value"])
            if "cache writes" in x["line_item"]:
                openai_cache_writes[day] += fnum(x["amount"]["value"])
    anthropic_inv = collections.defaultdict(float)
    for b in json.load(open(raw / "anthropic_cost_daily.json"))["data"]:
        for x in b["results"]:
            anthropic_inv[b["starting_at"][:10]] += fnum(x["amount_usd"])
    return openai_inv, openai_cache_writes, anthropic_inv


def load_users(raw: pathlib.Path):
    """Users snapshot, keeping the raw last_active dates so cohort is evaluated per usage day."""
    users = {}
    with open(raw / "users_active_30d.csv") as f:
        for r in csv.DictReader(f):
            users[r["uid_hash"]] = {
                "plan": r["plan"] or "none",
                "desktop": r["last_active_at_desktop"],
                "mobile": r["last_active_at_mobile"],
                "web": r["last_active_at_web"],
                "byok": (r.get("byok_active") or "").lower() == "true",
            }
    return users


def cohort_window_start_for(date: str, lookback_days: int, fixed: str | None = None) -> str:
    """The date from which a snapshot last_active_at_* counts as 'active on that platform'.

    Default: a trailing window of `lookback_days` ending on the usage day, so the definition is
    the same for every date whether it is computed alone or inside a backfill. `fixed` pins one
    explicit date instead, which is what reproducing an older report needs.
    """
    if fixed:
        return fixed
    return (dt.date.fromisoformat(date) - dt.timedelta(days=lookback_days - 1)).isoformat()


def load_facts(raw: pathlib.Path):
    fact = collections.defaultdict(
        lambda: {
            "llm": 0.0,
            "llm_openai": 0.0,
            "llm_gemini": 0.0,
            "llm_other": 0.0,
            "fc_desktop": 0.0,
            "attempts": 0,
            "unpriced": 0,
            "tx_sec": 0.0,
            "tier": None,
        }
    )
    with open(raw / "ledger_user_daily.csv") as f:
        for r in csv.DictReader(f):
            k = (r["date"], r["uid_hash"])
            fact[k]["llm"] += fnum(r["cost_micro_usd_sum"]) / 1e6
            fact[k]["llm_openai"] += fnum(r.get("cost_openai")) / 1e6
            fact[k]["llm_gemini"] += fnum(r.get("cost_gemini")) / 1e6
            fact[k]["llm_other"] += fnum(r.get("cost_other_provider")) / 1e6
            fact[k]["fc_desktop"] += fnum(r.get("fc_desktop")) / 1e6
            fact[k]["unpriced"] += int(r.get("attempts_unpriced") or 0)
            fact[k]["attempts"] += int(r["attempts"] or 0)
            fact[k]["tier"] = r["subscription_tier"] or r["plan_id"]
    with open(raw / "stt_usage_daily.csv") as f:
        for r in csv.DictReader(f):
            fact[(r["date"], r["uid_hash"])]["tx_sec"] += fnum(r["transcription_seconds"])
    return fact


def load_posthog(raw: pathlib.Path):
    ph = collections.defaultdict(lambda: collections.defaultdict(float))
    p = raw / "posthog_dau_daily.csv"
    if not p.exists():
        return ph
    with open(p) as f:
        for r in csv.DictReader(f):
            plat = "desktop" if r["os"] in ("macOS", "Windows") else "mobile"
            ph[r["definition"]][(r["day"], plat)] += int(r["users"])
    return ph


def load_vad_hours(raw: pathlib.Path):
    vad = collections.defaultdict(float)
    p = raw / "prom_stt_7d.json"
    if not p.exists():
        return vad
    try:
        pj = json.load(open(p))
        for series in pj["daily"]["d_vad_gate_audio_seconds"]["result"]["data"]["result"]:
            if series["metric"].get("outcome") == "sent":
                for ts, v in series["values"]:
                    day = (
                        (dt.datetime.fromtimestamp(int(ts), dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
                    )
                    vad[day] += fnum(v) / 3600
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("prom parse failed: %s\n" % e)
    return vad


# ---------------------------------------------------------------- roll-ups
def rollup(rows, keyfn, n_days: int):
    g = collections.defaultdict(lambda: collections.defaultdict(float))
    ud = collections.Counter()
    vals = collections.defaultdict(list)
    for r in rows:
        k = keyfn(r)
        ud[k] += 1
        for c_ in COMPS:
            g[k][c_] += r[c_]
        g[k]["tx_hours"] += r["tx_sec"] / 3600
        g[k]["attempts"] += r["attempts"]
        vals[k].append(r["variable_total"])
    out = []
    for k in sorted(g, key=lambda x: -g[x]["variable_total"]):
        n = ud[k]
        v = sorted(vals[k])
        row = {
            "segment": k if isinstance(k, str) else " / ".join(k),
            "user_days": n,
            "mean_users_per_day": round(n / n_days, 1),
        }
        for c_ in COMPS:
            row[c_ + "_per_day"] = round(g[k][c_] / n_days, 2)
        for c_ in (
            "variable_total",
            "variable_total_activity",
            "fully_loaded",
            "gross_total",
            "llm_openai_measured",
            "audio_pipeline_gcp",
            "shared_headcount",
            "stt_vendor_low",
            "stt_vendor_high",
            "vertex_pt_fixed",
        ):
            row[c_ + "_per_user_day"] = round(g[k][c_] / n, 4)
        row["variable_per_user_month_30d"] = round(g[k]["variable_total"] / n * 30, 2)
        row["p50_user_day"] = round(v[len(v) // 2], 4)
        row["p90_user_day"] = round(v[int(len(v) * 0.9)], 4)
        row["p99_user_day"] = round(v[int(len(v) * 0.99)], 4)
        row["top1pct_share"] = round(sum(v[-max(1, len(v) // 100) :]) / sum(v), 3) if sum(v) else 0
        row["tx_hours_per_user_day"] = round(g[k]["tx_hours"] / n, 3)
        row["attempts_per_user_day"] = round(g[k]["attempts"] / n, 1)
        out.append(row)
    return out


PLATFORM_UNION_MEMBERS = {
    "desktop_incl_dual": ("desktop_only", "dual"),
    "mobile_incl_dual": ("mobile_only", "dual"),
}


def long_rows(rows, date_of, segments):
    """Long-format (date, segment_type, segment, component) sums plus headcount.

    `segments` is a list of (segment_type, keyfn) where keyfn returns a segment name or a
    list of names (platform_union counts a dual user in both desktop and mobile).
    """
    agg = collections.defaultdict(lambda: collections.defaultdict(float))
    users = collections.defaultdict(set)
    for r in rows:
        d = date_of(r)
        for stype, keyfn in segments:
            k = keyfn(r)
            for seg in (k if isinstance(k, list) else [k]):
                if seg is None:
                    continue
                key = (d, stype, seg)
                users[key].add(r["uid_hash"])
                for c_ in COMPS:
                    agg[key][c_] += r[c_]
    out = []
    for d, stype, seg in sorted(agg):
        n = len(users[(d, stype, seg)])
        for c_ in COMPS:
            usd = agg[(d, stype, seg)][c_]
            out.append(
                {
                    "date": d,
                    "segment_type": stype,
                    "segment": seg,
                    "component": c_,
                    "method": METHOD[c_],
                    "usd": round(usd, 6),
                    "users": n,
                    "usd_per_user_day": round(usd / n, 8) if n else None,
                }
            )
    return out


def write_csv(path: pathlib.Path, rows: list) -> None:
    if not rows:
        path.write_text("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def assemble(
    raw: pathlib.Path,
    out: pathlib.Path,
    start: str,
    end: str,
    cohort_window_start: str | None = None,
    settled_through: str | None = None,
    cohort_lookback_days: int = 7,
) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    comp, dev_by_day, export_net, max_end = load_components(raw)
    openai_inv, openai_cache_writes, anthropic_inv = load_invoices(raw)
    users = load_users(raw)
    fact = load_facts(raw)
    ph = load_posthog(raw)
    vad_sent_h = load_vad_hours(raw)

    days = sorted(d for d in comp if start <= d <= end)
    if not days:
        raise SystemExit("no GCP component rows in window %s..%s" % (start, end))

    cohort_cache: dict[str, dict[str, str]] = {}

    def cohorts_on(date: str) -> dict:
        """Cohort per uid for one usage day, on that day's own activity window."""
        ws = cohort_window_start_for(date, cohort_lookback_days, cohort_window_start)
        if ws not in cohort_cache:
            cohort_cache[ws] = {uh: classify_cohort(u["desktop"], u["mobile"], u["web"], ws) for uh, u in users.items()}
        return cohort_cache[ws]

    def plan_of(uid, fallback="unknown"):
        return users.get(uid, {}).get("plan", fallback)

    rows, day_summary, recon_rows = [], {}, []
    for d in days:
        coh = cohorts_on(d)

        def cohort_of(uid, _c=coh):
            return _c.get(uid, "unknown")

        uids = [u for (dd, u) in fact if dd == d]
        n = len(uids)
        totals = {
            "openai": sum(fact[(d, u)]["llm_openai"] for u in uids),
            "gemini": sum(fact[(d, u)]["llm_gemini"] for u in uids),
            "desktop": sum(fact[(d, u)]["fc_desktop"] for u in uids),
            "tx_sec": sum(fact[(d, u)]["tx_sec"] for u in uids),
            "attempts": sum(fact[(d, u)]["attempts"] for u in uids),
        }
        residual_openai = openai_inv.get(d, 0) - totals["openai"]
        residual_anthropic = anthropic_inv.get(d, 0)  # no ledger rows: all direct-path
        c = dict(comp[d])
        pools = day_pools(c, residual_openai, residual_anthropic, vad_sent_h.get(d, 0))
        alloc_tot = collections.defaultdict(float)
        for u in uids:
            f_ = fact[(d, u)]
            r = {
                "date": d,
                "uid_hash": u,
                "cohort": cohort_of(u),
                "plan": plan_of(u, f_["tier"] or "unknown"),
                "attempts": f_["attempts"],
                "unpriced_attempts": f_["unpriced"],
                "tx_sec": f_["tx_sec"],
            }
            r.update(allocate_user_day(f_, pools, totals, n))
            for c_ in COMPS:
                alloc_tot[c_] += r[c_]
            rows.append(r)
        settled = settled_through is None or d <= settled_through
        recon_rows.extend(
            reconcile_day(
                d,
                pools,
                alloc_tot,
                c,
                export_net.get(d, sum(c.values())),
                openai_inv.get(d, 0),
                anthropic_inv.get(d, 0),
                settled,
            )
        )
        day_summary[d] = {
            "cost_active_users": n,
            "gcp_net": sum(c.values()),
            "gcp_net_excl_one_time": sum(v for k, v in c.items() if not is_one_time(k)),
            "gcp_one_time": sum(v for k, v in c.items() if is_one_time(k)),
            "gcp_export_net": export_net.get(d),
            "max_usage_end_time": max_end.get(d),
            "gcp_dev": dev_by_day.get(d, 0),
            "ledger_openai": totals["openai"],
            "ledger_gemini_list": totals["gemini"],
            "openai_invoice": openai_inv.get(d, 0),
            "openai_cache_writes": openai_cache_writes.get(d, 0),
            "anthropic_invoice": anthropic_inv.get(d, 0),
            "residual_openai": residual_openai,
            "tx_hours": totals["tx_sec"] / 3600,
            "vad_sent_hours": vad_sent_h.get(d, 0),
            "pools": pools,
            "inputs_settled": settled,
            "posthog_clean_desktop": ph["clean"].get((d, "desktop"), 0),
            "posthog_clean_mobile": ph["clean"].get((d, "mobile"), 0),
            "posthog_all_desktop": ph["all_events"].get((d, "desktop"), 0),
            "posthog_all_mobile": ph["all_events"].get((d, "mobile"), 0),
            "cohort_users": collections.Counter(cohort_of(u) for u in uids),
            "one_time_components": {k: v for k, v in c.items() if is_one_time(k)},
        }

    write_csv(out / "user_day_allocated.csv", rows)
    nd = len(days)
    by_cohort = rollup(rows, lambda r: r["cohort"], nd)
    by_plan = rollup(rows, lambda r: r["plan"], nd)
    by_cohort_plan = rollup(rows, lambda r: (r["cohort"], r["plan"]), nd)
    by_platform = rollup(
        rows,
        lambda r: (
            "desktop_incl_dual"
            if r["cohort"] in ("desktop_only", "dual")
            else "mobile_only" if r["cohort"] == "mobile_only" else "other"
        ),
        nd,
    )
    by_platform_m = rollup(
        rows,
        lambda r: (
            "mobile_incl_dual"
            if r["cohort"] in ("mobile_only", "dual")
            else "desktop_only" if r["cohort"] == "desktop_only" else "other"
        ),
        nd,
    )
    for name, table in (
        ("cohort", by_cohort),
        ("plan", by_plan),
        ("cohort_plan", by_cohort_plan),
        ("platform_union", by_platform),
        ("platform_union_m", by_platform_m),
    ):
        write_csv(out / ("unit_cost_by_%s.csv" % name), table)

    def platform_union_key(r):
        segs = [s for s, members in PLATFORM_UNION_MEMBERS.items() if r["cohort"] in members]
        return segs or ["other_union"]

    longs = long_rows(
        rows,
        lambda r: r["date"],
        [
            ("cohort", lambda r: r["cohort"]),
            ("plan", lambda r: r["plan"]),
            ("cohort_plan", lambda r: r["cohort"] + " / " + r["plan"]),
            ("platform_union", platform_union_key),
            ("total", lambda r: "all"),
        ],
    )
    # one-time charges: day level only, never per user
    for d in days:
        for k, v in day_summary[d]["one_time_components"].items():
            longs.append(
                {
                    "date": d,
                    "segment_type": "total",
                    "segment": "all",
                    "component": k,
                    "method": "one_time",
                    "usd": round(v, 6),
                    "users": day_summary[d]["cost_active_users"],
                    "usd_per_user_day": None,
                }
            )
    write_csv(out / "unit_cost_long.csv", longs)
    write_csv(out / "unit_cost_reconciliation.csv", recon_rows)

    alt = alt_denoms(rows, day_summary, days)
    write_csv(out / "platform_alt_denominators.csv", alt)
    json.dump(
        {
            "days": day_summary,
            "components_mean_per_day": {
                k: round(sum(comp[d].get(k, 0) for d in days) / nd, 2)
                for k in sorted({k for d in days for k in comp[d]})
            },
        },
        open(out / "day_summary.json", "w"),
        indent=1,
        default=str,
    )
    return {
        "days": days,
        "rows": rows,
        "day_summary": day_summary,
        "long": longs,
        "recon": recon_rows,
        "by_cohort": by_cohort,
        "by_plan": by_plan,
        "by_cohort_plan": by_cohort_plan,
        "by_platform": by_platform,
        "by_platform_m": by_platform_m,
        "alt": alt,
        "comp": comp,
    }


def alt_denoms(rows, day_summary, days):
    tot = collections.defaultdict(float)
    for r in rows:
        if r["cohort"] in ("desktop_only", "dual"):
            tot["desktop_incl_dual"] += r["variable_total"]
        if r["cohort"] in ("mobile_only", "dual"):
            tot["mobile_incl_dual"] += r["variable_total"]
    dd = {
        k: sum(day_summary[d][k] for d in days)
        for k in ("posthog_clean_desktop", "posthog_clean_mobile", "posthog_all_desktop", "posthog_all_mobile")
    }
    out = []
    for plat, keyc, keya in (
        ("desktop_incl_dual", "posthog_clean_desktop", "posthog_all_desktop"),
        ("mobile_incl_dual", "posthog_clean_mobile", "posthog_all_mobile"),
    ):
        members = PLATFORM_UNION_MEMBERS[plat]
        ud = sum(1 for r in rows if r["cohort"] in members)
        out.append(
            {
                "platform": plat,
                "variable_per_day": round(tot[plat] / len(days), 2),
                "per_cost_active_user_day": round(tot[plat] / ud, 3) if ud else None,
                "per_posthog_clean_dau": round(tot[plat] / dd[keyc], 3) if dd[keyc] else None,
                "per_posthog_all_events_dau": round(tot[plat] / dd[keya], 3) if dd[keya] else None,
                "mean_cost_active_users": round(ud / len(days)),
                "mean_posthog_clean_dau": round(dd[keyc] / len(days)),
                "mean_posthog_all_dau": round(dd[keya] / len(days)),
            }
        )
    return out


def report(res: dict, start: str, end: str) -> None:
    days, day_summary = res["days"], res["day_summary"]

    def show(title, table, cols):
        print(f"\n## {title}")
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for r in table:
            print("| " + " | ".join(str(r[c]) for c in cols) + " |")

    print(f"# Omi unit cost, usage days {start}..{end} ({len(days)} days)")
    print("\n## Day summary")
    for d in days:
        s = day_summary[d]
        print(
            f"{d}: cost-active {s['cost_active_users']}  gcp ${s['gcp_net_excl_one_time']:.0f}"
            f" (one-time ${s['gcp_one_time']:.0f}, dev ${s['gcp_dev']:.0f})"
            f"  ledger openai ${s['ledger_openai']:.0f} gemini-list ${s['ledger_gemini_list']:.0f}"
            f"  openai inv ${s['openai_invoice']:.0f} (cache-writes ${s['openai_cache_writes']:.0f})"
            f" resid ${s['residual_openai']:.0f}  anthropic inv ${s['anthropic_invoice']:.0f}"
            f"  tx {s['tx_hours']:.0f}h vad-sent {s['vad_sent_hours']:.0f}h"
            f"  posthog clean D/M {s['posthog_clean_desktop']:.0f}/{s['posthog_clean_mobile']:.0f}"
            f"  cohorts {dict(s['cohort_users'])}"
        )
    print("\n## GCP components mean $/day")
    comp = res["comp"]
    means = {k: sum(comp[d].get(k, 0) for d in days) / len(days) for k in sorted({k for d in days for k in comp[d]})}
    for k, v in sorted(means.items(), key=lambda x: -x[1]):
        print(f"  {k:28s} {v:8.2f}{'   [one_time, excluded from run rate]' if is_one_time(k) else ''}")
    print("\n## Reconciliation (allocated vs pool)")
    print("| date | pool | pool_usd | allocated_usd | delta_pct | source |")
    print("|---|---|---:|---:|---:|---|")
    for r in res["recon"]:
        print(
            f"| {r['date']} | {r['pool']} | {r['pool_usd']:.2f} | {r['allocated_usd']:.2f} |"
            f" {r['delta_pct']:.4f} | {r['invoice_source']} |"
        )
    C1 = [
        "segment",
        "mean_users_per_day",
        "variable_total_per_day",
        "variable_total_per_user_day",
        "variable_total_activity_per_user_day",
        "fully_loaded_per_user_day",
        "variable_per_user_month_30d",
        "p50_user_day",
        "p90_user_day",
        "p99_user_day",
        "top1pct_share",
    ]
    C2 = [
        "segment",
        "llm_openai_measured_per_day",
        "llm_direct_residual_per_day",
        "vertex_paygo_per_day",
        "audio_pipeline_gcp_per_day",
        "desktop_pools_per_day",
        "shared_headcount_per_day",
        "variable_total_per_day",
        "vertex_pt_fixed_per_day",
        "llm_gemini_list_memo_per_day",
        "stt_vendor_low_per_day",
        "stt_vendor_high_per_day",
        "tx_hours_per_user_day",
        "attempts_per_user_day",
    ]
    show("By platform cohort: unit cost", res["by_cohort"], C1)
    show("By platform cohort: components $/day", res["by_cohort"], C2)
    show("By plan: unit cost", res["by_plan"], C1)
    show("By plan: components $/day", res["by_plan"], C2)
    show("By cohort x plan (top 15)", res["by_cohort_plan"][:15], C1)
    show("Platform union views (dual counted in both)", res["by_platform"] + res["by_platform_m"], C1)
    show("Platform totals under alternative denominators", res["alt"], list(res["alt"][0].keys()))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", nargs="?", default="raw")
    ap.add_argument("out", nargs="?", default="derived")
    ap.add_argument("start", nargs="?", default=None)
    ap.add_argument("end", nargs="?", default=None)
    ap.add_argument(
        "cohort_window_start",
        nargs="?",
        default=None,
        help="pin the date from which a users-snapshot last_active_at_* counts as 'on that platform'. "
        "Omit for the default trailing window (--cohort-lookback-days ending on each usage day).",
    )
    ap.add_argument("--settled-through", default=None)
    ap.add_argument("--cohort-lookback-days", type=int, default=7)
    a = ap.parse_args(argv)
    raw, out = pathlib.Path(a.raw), pathlib.Path(a.out)
    start = a.start or min(r["usage_day"] for r in json.load(open(raw / "gcp_components_daily.json")))
    end = a.end or max(r["usage_day"] for r in json.load(open(raw / "gcp_components_daily.json")))
    res = assemble(raw, out, start, end, a.cohort_window_start, a.settled_through, a.cohort_lookback_days)
    report(res, start, end)


if __name__ == "__main__":
    main()
