#!/usr/bin/env python3
"""Pull llm_gateway_attempts from prod Firestore and aggregate to per-day CSVs.

Read-only. Dependency-free (stdlib only). Never writes raw user_uid to disk:
uids are hashed sha256(uid)[:16] in flight.

Usage:
  python3 pull_ledger.py --out DIR --dates 2026-09-06 [2026-09-05 ...]
Optional: --page-size 5000 --project based-hardware --collection llm_gateway_attempts
"""

import argparse, collections, csv, hashlib, json, os, subprocess, sys, time, urllib.error, urllib.request

PROJECT_DEFAULT = "based-hardware"
COLLECTION_DEFAULT = "llm_gateway_attempts"
ENV_SCRIPT = os.path.expanduser("~/.hermes/scripts/omi-prod-gcp-read-only-env.sh")

FIELDS = [
    "user_uid",
    "app_platform",
    "feature",
    "subscription_tier",
    "plan_id",
    "provider",
    "payer",
    "caller",
    "cost_status",
    "cost_attribution_status",
    "estimated_cost_micro_usd",
    "prompt_tokens",
    "cached_input_tokens",
    "output_tokens",
    "outcome",
    "configured_model",
    "rate_card_id",
]

GROUP_KEYS = [
    "app_platform",
    "feature",
    "subscription_tier",
    "plan_id",
    "provider",
    "payer",
    "caller",
    "cost_status",
    "cost_attribution_status",
]

UNATTR = "unattributed"


def get_token():
    """Bearer token from the read-only bot profile (subshell: the env script clobbers PATH)."""
    out = subprocess.run(
        ["bash", "-c", 'source "%s" >/dev/null 2>&1; gcloud auth print-access-token' % ENV_SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
    )
    tok = out.stdout.strip()
    if not tok:
        raise RuntimeError("token fetch failed: %s" % out.stderr[-500:])
    return tok


def sval(f):
    """Scalar value out of a Firestore typed field."""
    if f is None:
        return None
    if "stringValue" in f:
        return f["stringValue"]
    if "integerValue" in f:
        return int(f["integerValue"])
    if "doubleValue" in f:
        return f["doubleValue"]
    if "booleanValue" in f:
        return f["booleanValue"]
    if "nullValue" in f:
        return None
    return None


def s(v):
    return "" if v is None else str(v)


def i(v):
    return v if isinstance(v, int) else 0


class Api:
    def __init__(self, project, collection, timeout=300):
        self.base = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents" % project
        self.collection = collection
        self.timeout = timeout
        self.token = get_token()
        self.doc_prefix = self.base + "/" + collection + "/"

    def _post(self, url, body, attempt_refresh=True):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt_refresh:
                sys.stderr.write("  [401] refreshing token\n")
                self.token = get_token()
                return self._post(url, body, attempt_refresh=False)
            raise

    def post_retry(self, url, body, tries=3):
        last = None
        for n in range(tries):
            try:
                return self._post(url, body)
            except Exception as e:
                last = e
                detail = ""
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        detail = e.read().decode()[:300]
                    except Exception:
                        pass
                sys.stderr.write("  [retry %d/%d] %s %s\n" % (n + 1, tries, e, detail))
                time.sleep(3 * (n + 1))
        raise last

    def page(self, date, page_size, start_after=None):
        q = {
            "from": [{"collectionId": self.collection}],
            "select": {"fields": [{"fieldPath": f} for f in FIELDS]},
            "where": {"fieldFilter": {"field": {"fieldPath": "date"}, "op": "EQUAL", "value": {"stringValue": date}}},
            "orderBy": [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}],
            "limit": page_size,
        }
        if start_after:
            q["startAt"] = {"values": [{"referenceValue": start_after}], "before": False}
        return self.post_retry(self.base + ":runQuery", {"structuredQuery": q})

    def aggregate(self, date):
        q = {
            "structuredQuery": {
                "from": [{"collectionId": self.collection}],
                "where": {
                    "fieldFilter": {"field": {"fieldPath": "date"}, "op": "EQUAL", "value": {"stringValue": date}}
                },
            },
            "aggregations": [
                {"alias": "cnt", "count": {}},
                {"alias": "cost", "sum": {"field": {"fieldPath": "estimated_cost_micro_usd"}}},
            ],
        }
        res = self.post_retry(self.base + ":runAggregationQuery", {"structuredAggregationQuery": q})
        cnt = cost = None
        for chunk in res:
            agg = chunk.get("result", {}).get("aggregateFields", {})
            if "cnt" in agg:
                cnt = sval(agg["cnt"])
            if "cost" in agg:
                cost = sval(agg["cost"])
        return cnt, cost


class DayAgg:
    """Streaming aggregator: one day of rows in, three shapes of summary out."""

    def __init__(self, date):
        self.date = date
        self.groups = collections.defaultdict(
            lambda: {"attempts": 0, "cost": 0, "pt": 0, "ct": 0, "ot": 0, "uids": set()}
        )
        self.users = collections.defaultdict(
            lambda: {
                "attempts": 0,
                "cost": 0,
                "plat": collections.Counter(),
                "tier": collections.Counter(),
                "plan": collections.Counter(),
                "prov": collections.Counter(),
                "fc": collections.Counter(),
                "unpriced": 0,
            }
        )
        self.attempts = 0
        self.cost = 0
        self.cost_omi = 0
        self.cost_unattr = 0
        self.attempts_unattr = 0

    def add(self, f):
        plat = sval(f.get("app_platform")) or UNATTR
        uid = sval(f.get("user_uid"))
        uh = hashlib.sha256(uid.encode()).hexdigest()[:16] if uid else "anonymous"
        cost = i(sval(f.get("estimated_cost_micro_usd")))
        tier = s(sval(f.get("subscription_tier")))
        plan = s(sval(f.get("plan_id")))

        key = (
            plat,
            s(sval(f.get("feature"))),
            tier,
            plan,
            s(sval(f.get("provider"))),
            s(sval(f.get("payer"))),
            s(sval(f.get("caller"))),
            s(sval(f.get("cost_status"))),
            s(sval(f.get("cost_attribution_status"))),
        )
        g = self.groups[key]
        g["attempts"] += 1
        g["cost"] += cost
        g["pt"] += i(sval(f.get("prompt_tokens")))
        g["ct"] += i(sval(f.get("cached_input_tokens")))
        g["ot"] += i(sval(f.get("output_tokens")))
        g["uids"].add(uh)

        u = self.users[uh]
        u["attempts"] += 1
        u["cost"] += cost
        u["plat"][plat] += 1
        u["tier"][tier] += 1
        u["plan"][plan] += 1
        prov = s(sval(f.get("provider")))
        u["prov"][prov] += cost
        feat = s(sval(f.get("feature")))
        fc = (
            "desktop"
            if feat.startswith("desktop_")
            else (
                "proactive_notification"
                if feat == "proactive_notification"
                else (
                    "chat"
                    if feat.startswith("chat") or feat.startswith("persona")
                    else (
                        "translation"
                        if feat == "translation"
                        else "embeddings" if "embedding" in feat else "extraction"
                    )
                )
            )
        )
        u["fc"][fc] += cost
        if s(sval(f.get("cost_status"))) != "estimated":
            u["unpriced"] += 1

        self.attempts += 1
        self.cost += cost
        if s(sval(f.get("payer"))) == "omi":
            self.cost_omi += cost
        if plat == UNATTR:
            self.cost_unattr += cost
            self.attempts_unattr += 1


def open_csv(path, header):
    new = not os.path.exists(path)
    fh = open(path, "a", newline="")
    w = csv.writer(fh)
    if new:
        w.writerow(header)
    return fh, w


def run_day(api, date, out, page_size):
    t0 = time.time()
    agg = DayAgg(date)
    cursor, pages = None, 0
    while True:
        res = api.page(date, page_size, cursor)
        got, last = 0, None
        for chunk in res:
            doc = chunk.get("document")
            if not doc:
                continue
            got += 1
            last = doc["name"]
            agg.add(doc.get("fields", {}))
        pages += 1
        if pages % 10 == 0 or got < page_size:
            sys.stderr.write(
                "  %s page %d rows=%d total=%d %.0fs\n" % (date, pages, got, agg.attempts, time.time() - t0)
            )
            sys.stderr.flush()
        if got < page_size or last is None:
            break
        cursor = last

    agg_count, agg_cost = api.aggregate(date)
    elapsed = time.time() - t0

    fh, w = open_csv(
        os.path.join(out, "ledger_agg_daily.csv"),
        ["date"]
        + GROUP_KEYS
        + [
            "attempts",
            "cost_micro_usd_sum",
            "prompt_tokens_sum",
            "cached_input_tokens_sum",
            "output_tokens_sum",
            "distinct_uids",
        ],
    )
    for k, g in sorted(agg.groups.items(), key=lambda kv: -kv[1]["cost"]):
        w.writerow([date] + list(k) + [g["attempts"], g["cost"], g["pt"], g["ct"], g["ot"], len(g["uids"])])
    fh.close()

    fh, w = open_csv(
        os.path.join(out, "ledger_user_daily.csv"),
        [
            "date",
            "uid_hash",
            "app_platform_mode",
            "platforms_seen",
            "subscription_tier",
            "plan_id",
            "attempts",
            "cost_micro_usd_sum",
            "cost_openai",
            "cost_gemini",
            "cost_other_provider",
            "attempts_unpriced",
            "fc_desktop",
            "fc_proactive_notification",
            "fc_extraction",
            "fc_chat",
            "fc_translation",
            "fc_embeddings",
        ],
    )
    for uh, u in sorted(agg.users.items(), key=lambda kv: -kv[1]["cost"]):
        pv = u["prov"]
        fc = u["fc"]
        w.writerow(
            [
                date,
                uh,
                u["plat"].most_common(1)[0][0],
                "|".join(sorted(u["plat"])),
                u["tier"].most_common(1)[0][0],
                u["plan"].most_common(1)[0][0],
                u["attempts"],
                u["cost"],
                pv.get("openai", 0),
                pv.get("gemini", 0),
                sum(v for k, v in pv.items() if k not in ("openai", "gemini")),
                u["unpriced"],
                fc.get("desktop", 0),
                fc.get("proactive_notification", 0),
                fc.get("extraction", 0),
                fc.get("chat", 0),
                fc.get("translation", 0),
                fc.get("embeddings", 0),
            ]
        )
    fh.close()

    fh, w = open_csv(
        os.path.join(out, "ledger_daily_totals.csv"),
        [
            "date",
            "attempts",
            "cost_usd_total",
            "cost_usd_payer_omi",
            "cost_usd_unattributed_platform",
            "attempts_unattributed_platform",
            "share_unattributed",
            "agg_count",
            "agg_cost_usd",
            "distinct_uids",
            "wall_seconds",
        ],
    )
    w.writerow(
        [
            date,
            agg.attempts,
            round(agg.cost / 1e6, 6),
            round(agg.cost_omi / 1e6, 6),
            round(agg.cost_unattr / 1e6, 6),
            agg.attempts_unattr,
            round(agg.attempts_unattr / agg.attempts, 6) if agg.attempts else 0,
            agg_count,
            round((agg_cost or 0) / 1e6, 6),
            len(agg.users),
            round(elapsed, 1),
        ]
    )
    fh.close()

    sys.stderr.write(
        "DONE %s attempts=%d agg_count=%s cost=$%.2f agg_cost=$%.2f uids=%d %.0fs\n"
        % (date, agg.attempts, agg_count, agg.cost / 1e6, (agg_cost or 0) / 1e6, len(agg.users), elapsed)
    )
    sys.stderr.flush()
    return elapsed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--dates", nargs="+", required=True)
    p.add_argument("--page-size", type=int, default=5000)
    p.add_argument("--project", default=PROJECT_DEFAULT)
    p.add_argument("--collection", default=COLLECTION_DEFAULT)
    p.add_argument("--max-day-seconds", type=float, default=1500.0)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    api = Api(a.project, a.collection)
    for d in a.dates:
        el = run_day(api, d, a.out, a.page_size)
        if el > a.max_day_seconds:
            sys.stderr.write("STOP: %s took %.0fs (> %.0fs budget)\n" % (d, el, a.max_day_seconds))
            break


if __name__ == "__main__":
    main()
