"""End-to-end last-30-day cost + revenue + per-platform attribution report.

Sources, in priority order:

  1) GCP — BigQuery `gcp_billing_export` over both billing accounts. This is
     the authoritative invoice number. We split per service.
  2) Firestore — collection group `llm_usage`, sum `cost_usd` on every
     `bucket.{cost_usd}` field. This is authoritative for backend-routed LLM
     calls (chat / RAG / proactive notifications). Bucket names already
     carry a `desktop_` / `mobile_` prefix so platform attribution is exact.
  3) Stripe — active subscriptions, joined to Firestore `users.signup_platform`
     for revenue split.
  4) External providers (Anthropic / OpenAI / Deepgram / OpenRouter) — fall
     back to the team-beasts daily report's 7-day totals × 2 ≈ MTD actual
     when we can't pull live admin APIs (current keys are project-scoped, not
     org-admin).

Platform allocation rules (when a service can't be attributed exactly):

   service                         desktop  mobile   why
   ------------------------------- -------  ------   ----------------------
   Firestore llm_usage cost_usd      exact   exact   bucket prefix
   Stripe MRR                        exact   exact   uid → signup_platform
   GCP Translate                     0%      100%    mobile-only feature
   GCP Gemini API + Vertex AI        90%     10%     desktop Live Notes +
                                                     embeddings + proactive
   GCP Cloud Run / App Engine /      DAU     DAU     shared backend, split
       Compute Engine / Storage     ratio   ratio    by macOS vs iOS+Android
       (Networking / Logging /                      DAU on the report day
       PubSub / Geocoding /                          (27% / 73%)
       BigQuery / Monitoring /
       Artifact / KMS / Secret /
       Cloud Run Functions /
       Cloud Build / VM Manager /
       Container Registry)
   Anthropic                         90%     10%     desktop Claude floating
                                                     bar
   OpenAI                            50%     50%     chat on both platforms
   Deepgram                          20%     80%     mobile audio pipeline

Usage:
    python scripts/cost_report.py
    python scripts/cost_report.py --json /tmp/cost_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Tuple

import firebase_admin
from firebase_admin import firestore
from google.cloud import bigquery

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

GCP_PROJECT = 'based-hardware'
BILLING_TABLES = [
    'based-hardware.gcp_billing_export.gcp_billing_export_v1_01B287_9348DC_02D256',
    'based-hardware.gcp_billing_export.gcp_billing_export_v1_01B896_918303_539138',
]

# DAU split from the team-beasts Apr 17 daily report:
#   macOS 2,651  /  iOS 5,241 + Android 2,408 = 7,649
#   total 10,300 → desktop 25.7%, mobile 74.3%
DAU_DESKTOP_SHARE = 0.257
DAU_MOBILE_SHARE = 0.743

# Platform-weight overrides per GCP service (sum should be ≈ 1.0).
GCP_PLATFORM_WEIGHTS: Dict[str, Tuple[float, float]] = {
    'Translate': (0.0, 1.0),  # mobile-only feature
    'Gemini API': (0.9, 0.1),  # desktop Live Notes + embeddings + proactive
    'Vertex AI': (0.9, 0.1),  # same as Gemini
    'Geocoding API': (0.0, 1.0),  # mobile geo features
    'Maps Static API': (0.0, 1.0),
}

# External-provider reference numbers from the team-beasts Apr 17 daily
# report's "7-Day Cost Trends (All Providers)" section. We use 7-day × 2 ≈
# MTD actual which lines up with codex's daily audit and avoids amplifying
# the Anthropic Apr 16 15x spike. Override via env vars below.
EXTERNAL_REFERENCE = {
    'Anthropic': {'cost_30d': 14326.0, 'desktop_share': 0.9, 'mobile_share': 0.1},
    'OpenAI': {'cost_30d': 14884.0, 'desktop_share': 0.5, 'mobile_share': 0.5},
    'Deepgram': {'cost_30d': 10580.0, 'desktop_share': 0.2, 'mobile_share': 0.8},
}

# ----------------------------------------------------------------------------
# Output dataclasses
# ----------------------------------------------------------------------------


@dataclass
class CostRow:
    service: str
    gross_usd: float
    credits_usd: float
    net_usd: float
    desktop_usd: float
    mobile_usd: float
    method: str  # how we attributed to platforms — e.g. "DAU split", "exact"


@dataclass
class Report:
    window_days: int = 30
    gcp_rows: list = field(default_factory=list)
    firestore_llm_rows: list = field(default_factory=list)
    external_reference_rows: list = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_desktop_usd: float = 0.0
    total_mobile_usd: float = 0.0
    revenue_total: float = 0.0
    revenue_desktop: float = 0.0
    revenue_mobile: float = 0.0
    revenue_unknown: float = 0.0
    n_active_subs: int = 0
    n_users_with_platform: int = 0
    notes: list = field(default_factory=list)

    def add(self, row: CostRow):
        self.total_cost_usd += row.net_usd
        self.total_desktop_usd += row.desktop_usd
        self.total_mobile_usd += row.mobile_usd


# ----------------------------------------------------------------------------
# Source 1: GCP via BigQuery billing export
# ----------------------------------------------------------------------------


def fetch_gcp_costs(window_days: int) -> Iterable[CostRow]:
    bq = bigquery.Client(project=GCP_PROJECT)
    union = ' UNION ALL '.join(
        f'SELECT service.description AS service, cost, credits FROM `{t}` '
        f'WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_days} DAY)'
        for t in BILLING_TABLES
    )
    sql = f"""
        WITH a AS ({union})
        SELECT
          service,
          ROUND(SUM(cost), 2) AS gross_usd,
          ROUND(SUM(IFNULL((SELECT SUM(amount) FROM UNNEST(credits)), 0)), 2) AS credits_usd
        FROM a
        GROUP BY service
        HAVING gross_usd > 0
        ORDER BY gross_usd DESC
    """
    job = bq.query(sql)
    for r in job.result():
        service = r['service']
        gross = float(r['gross_usd'] or 0.0)
        credits_usd = float(r['credits_usd'] or 0.0)
        net = round(gross + credits_usd, 2)
        d_share, m_share = GCP_PLATFORM_WEIGHTS.get(service, (DAU_DESKTOP_SHARE, DAU_MOBILE_SHARE))
        method = 'DAU split' if service not in GCP_PLATFORM_WEIGHTS else 'service-specific weight'
        yield CostRow(
            service=f'GCP / {service}',
            gross_usd=gross,
            credits_usd=credits_usd,
            net_usd=net,
            desktop_usd=round(net * d_share, 2),
            mobile_usd=round(net * m_share, 2),
            method=method,
        )


# ----------------------------------------------------------------------------
# Source 2: Firestore llm_usage cost_usd buckets
# ----------------------------------------------------------------------------


def fetch_firestore_llm_costs(window_days: int) -> Iterable[CostRow]:
    db = firestore.client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    cutoff_id = f'{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}'
    by_bucket: Dict[str, float] = defaultdict(float)
    n_docs = 0
    for doc in db.collection_group('llm_usage').where('date', '>=', cutoff_id).stream():
        n_docs += 1
        data = doc.to_dict() or {}
        for key, value in data.items():
            if key in ('date', 'last_updated'):
                continue
            if not isinstance(value, dict):
                continue
            cost = value.get('cost_usd')
            if not isinstance(cost, (int, float)) or cost <= 0:
                continue
            # Skip alias buckets like `desktop_chat_omi` — they're already in
            # the primary `desktop_chat` bucket.
            if key.count('_') > 1:
                continue
            by_bucket[key] += float(cost)

    for bucket, cost in sorted(by_bucket.items(), key=lambda x: -x[1]):
        platform = 'unknown'
        d_share = m_share = 0.5
        if bucket.startswith('desktop_'):
            platform = 'desktop'
            d_share, m_share = 1.0, 0.0
        elif bucket.startswith('mobile_'):
            platform = 'mobile'
            d_share, m_share = 0.0, 1.0
        yield CostRow(
            service=f'Firestore llm_usage / {bucket}',
            gross_usd=round(cost, 2),
            credits_usd=0.0,
            net_usd=round(cost, 2),
            desktop_usd=round(cost * d_share, 2),
            mobile_usd=round(cost * m_share, 2),
            method=f'bucket prefix → {platform}',
        )


# ----------------------------------------------------------------------------
# Source 3: External providers — reference numbers
# ----------------------------------------------------------------------------


def fetch_external_reference() -> Iterable[CostRow]:
    """Static fallback values for providers we couldn't pull live (no admin
    API keys). Sourced from the team-beasts daily report 7-day × 2 ≈ MTD."""
    for name, vals in EXTERNAL_REFERENCE.items():
        cost = float(vals['cost_30d'])
        d = float(vals['desktop_share'])
        m = float(vals['mobile_share'])
        yield CostRow(
            service=f'External / {name}',
            gross_usd=cost,
            credits_usd=0.0,
            net_usd=cost,
            desktop_usd=round(cost * d, 2),
            mobile_usd=round(cost * m, 2),
            method=f'team-beasts 7-day×2 ({int(d * 100)}/{int(m * 100)} weight)',
        )


# ----------------------------------------------------------------------------
# Revenue: Stripe → user platform
# ----------------------------------------------------------------------------


def fetch_revenue_split(report: Report) -> None:
    import stripe

    stripe_key = os.environ.get('STRIPE_SECRET_KEY')
    monthly_price = os.environ.get('STRIPE_UNLIMITED_MONTHLY_PRICE_ID')
    annual_price = os.environ.get('STRIPE_UNLIMITED_ANNUAL_PRICE_ID')
    if not stripe_key or not monthly_price or not annual_price:
        report.notes.append(
            'Stripe env vars missing — revenue not pulled. Set STRIPE_SECRET_KEY '
            'and STRIPE_UNLIMITED_{MONTHLY,ANNUAL}_PRICE_ID.'
        )
        return

    stripe.api_key = stripe_key
    db = firestore.client()

    by_platform = {'desktop': 0.0, 'mobile': 0.0, 'unknown': 0.0}
    n_subs = 0

    for price_id in (monthly_price, annual_price):
        monthly_divider = 12 if price_id == annual_price else 1
        starting_after = None
        while True:
            kwargs = dict(status='active', price=price_id, limit=100, expand=['data.items.data.price'])
            if starting_after:
                kwargs['starting_after'] = starting_after
            page = stripe.Subscription.list(**kwargs)
            for sub in page.data:
                n_subs += 1
                uid = (sub.metadata or {}).get('uid')
                platform = 'unknown'
                if uid:
                    snap = db.collection('users').document(uid).get()
                    if snap.exists:
                        d = snap.to_dict() or {}
                        platform = d.get('signup_platform') or d.get('last_active_platform') or 'unknown'
                        # Fallback: if signup_platform missing but platforms_used set, take first.
                        if platform == 'unknown':
                            used = d.get('platforms_used') or []
                            if used:
                                platform = used[0]
                amount = 0.0
                items_obj = sub['items']
                items_data = items_obj['data'] if isinstance(items_obj, dict) else items_obj.data
                for item in items_data:
                    price = item.get('price') if isinstance(item, dict) else item.price
                    if not price:
                        continue
                    unit_amount = (price.get('unit_amount') if isinstance(price, dict) else price.unit_amount) or 0
                    quantity = (item.get('quantity') if isinstance(item, dict) else item.quantity) or 1
                    amount += (unit_amount * quantity) / 100.0
                mrr = amount / monthly_divider
                if platform not in by_platform:
                    platform = 'unknown'
                by_platform[platform] += mrr
            if not page.has_more or len(page.data) == 0:
                break
            starting_after = page.data[-1].id

    report.revenue_total = round(sum(by_platform.values()), 2)
    report.revenue_desktop = round(by_platform['desktop'], 2)
    report.revenue_mobile = round(by_platform['mobile'], 2)
    report.revenue_unknown = round(by_platform['unknown'], 2)
    report.n_active_subs = n_subs


# ----------------------------------------------------------------------------
# Backfill summary helper
# ----------------------------------------------------------------------------


def count_users_with_platform(report: Report) -> None:
    db = firestore.client()
    # Cheap aggregation via collection_group on platforms_used isn't possible
    # without an index; just probe a few hundred users for diagnostic only.
    sample = list(db.collection('users').limit(1000).stream())
    n = sum(1 for s in sample if (s.to_dict() or {}).get('signup_platform'))
    report.n_users_with_platform = n
    report.notes.append(f'Sample of 1000 users: {n} ({100 * n / max(len(sample), 1):.1f}%) have signup_platform set.')


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def render_report(report: Report) -> str:
    out = []
    out.append('=' * 78)
    out.append(f' OMI cost / revenue / platform-split report — last {report.window_days} days')
    out.append(f' Generated: {datetime.now(timezone.utc).isoformat()}Z')
    out.append('=' * 78)

    def section(title: str):
        out.append('')
        out.append(f'─── {title} '.ljust(78, '─'))

    def row(name: str, total: float, desktop: float, mobile: float, method: str = ''):
        out.append(
            f'  {name:<48} ${total:>10,.0f}  D=${desktop:>9,.0f}  M=${mobile:>9,.0f}'
            + (f'   [{method}]' if method else '')
        )

    section('GCP (BigQuery billing export — both accounts, gross + credits)')
    gcp_total = sum(r.net_usd for r in report.gcp_rows)
    for r in report.gcp_rows:
        row(r.service, r.net_usd, r.desktop_usd, r.mobile_usd, r.method)
    out.append(f'  {"GCP subtotal":<48} ${gcp_total:>10,.0f}')

    section('Firestore llm_usage — exact per-platform from bucket prefix')
    fs_total = sum(r.net_usd for r in report.firestore_llm_rows)
    if not report.firestore_llm_rows:
        out.append('  (no rows — collection group scan returned 0 cost_usd entries)')
    for r in report.firestore_llm_rows:
        row(r.service, r.net_usd, r.desktop_usd, r.mobile_usd, r.method)
    out.append(f'  {"Firestore llm_usage subtotal":<48} ${fs_total:>10,.0f}')

    section('External providers (no admin API keys → reference values)')
    ext_total = sum(r.net_usd for r in report.external_reference_rows)
    for r in report.external_reference_rows:
        row(r.service, r.net_usd, r.desktop_usd, r.mobile_usd, r.method)
    out.append(f'  {"External subtotal":<48} ${ext_total:>10,.0f}')

    section('TOTALS')
    out.append(
        f'  {"COST (last 30d)":<48} ${report.total_cost_usd:>10,.0f}  '
        f'D=${report.total_desktop_usd:>9,.0f}  M=${report.total_mobile_usd:>9,.0f}'
    )
    out.append(
        f'  {"REVENUE (current MRR / Stripe active)":<48} ${report.revenue_total:>10,.0f}  '
        f'D=${report.revenue_desktop:>9,.0f}  M=${report.revenue_mobile:>9,.0f}'
        + (f'  unknown=${report.revenue_unknown:>5,.0f}' if report.revenue_unknown else '')
    )
    net_total = report.revenue_total - report.total_cost_usd
    net_desktop = report.revenue_desktop - report.total_desktop_usd
    net_mobile = report.revenue_mobile - report.total_mobile_usd
    out.append(
        f'  {"NET (revenue − cost)":<48} ${net_total:>10,.0f}  ' f'D=${net_desktop:>9,.0f}  M=${net_mobile:>9,.0f}'
    )
    if report.total_cost_usd > 0:
        ratio = report.revenue_total / report.total_cost_usd
        out.append(f'  {"Revenue / cost ratio":<48} {ratio:>10.2f}x')

    section('NOTES')
    for n in report.notes:
        out.append(f'  • {n}')

    section('PLATFORM ATTRIBUTION GAPS — backend changes that close them')
    out.append(
        '  • OpenAI / Anthropic / Deepgram are pulled from a static reference table\n'
        '    today. Wire `record_llm_usage_bucket(uid, ..., bucket=…, cost_usd=…)`\n'
        '    in every backend caller (utils/llm/*, utils/stt/*) so live spend\n'
        '    flows into Firestore `llm_usage` with platform-specific buckets.\n'
        '    Result: this report becomes 100% live, no reference table.'
    )
    out.append(
        '  • Mobile LLM buckets are not written today (backend hardcodes\n'
        '    `desktop_*`). Add a platform parameter sourced from `X-App-Platform`\n'
        '    so calls become `mobile_chat`, `mobile_proactive`, etc.'
    )
    out.append(
        '  • GCP service splits use a coarse 27/73 DAU ratio for shared infra\n'
        '    (Compute Engine, App Engine, Cloud Run, Storage, Networking).\n'
        '    For exact attribution, add GCP labels {team, platform} on every\n'
        '    workload (Helm charts already support `commonLabels`) and BQ sums\n'
        '    by label. Then GCP becomes exact too.'
    )
    out.append(
        '  • Mercury bank is not pulled — we don\'t have an API token. If you\n'
        '    drop one in GCP Secret Manager as MERCURY_API_TOKEN, this CLI can\n'
        '    cross-check by category (Anthropic, OpenAI, Vendor X, etc.) for a\n'
        '    full ground-truth bill.'
    )

    out.append('')
    out.append('=' * 78)
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--json', help='Also write a JSON file with the same data')
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    report = Report(window_days=args.days)

    print('… pulling GCP billing (BigQuery, both accounts) …', file=sys.stderr, flush=True)
    for r in fetch_gcp_costs(args.days):
        report.gcp_rows.append(r)
        report.add(r)

    print('… scanning Firestore llm_usage cost_usd buckets …', file=sys.stderr, flush=True)
    for r in fetch_firestore_llm_costs(args.days):
        report.firestore_llm_rows.append(r)
        report.add(r)

    print('… loading external-provider reference table …', file=sys.stderr, flush=True)
    for r in fetch_external_reference():
        report.external_reference_rows.append(r)
        report.add(r)

    print('… computing Stripe revenue split …', file=sys.stderr, flush=True)
    fetch_revenue_split(report)

    print('… sampling user signup_platform coverage …', file=sys.stderr, flush=True)
    count_users_with_platform(report)

    txt = render_report(report)
    print(txt)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(
                {
                    'window_days': report.window_days,
                    'total_cost_usd': report.total_cost_usd,
                    'total_desktop_usd': report.total_desktop_usd,
                    'total_mobile_usd': report.total_mobile_usd,
                    'revenue_total': report.revenue_total,
                    'revenue_desktop': report.revenue_desktop,
                    'revenue_mobile': report.revenue_mobile,
                    'revenue_unknown': report.revenue_unknown,
                    'n_active_subs': report.n_active_subs,
                    'rows': [
                        r.__dict__
                        for r in (report.gcp_rows + report.firestore_llm_rows + report.external_reference_rows)
                    ],
                    'notes': report.notes,
                    'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
                },
                f,
                indent=2,
            )
        print(f'\nJSON written to {args.json}', file=sys.stderr)


if __name__ == '__main__':
    main()
