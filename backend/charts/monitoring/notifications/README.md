# Telegram pages and warning digest

The committed fleet measured on 2026-10-13 has 124 rules: 46 critical,
60 warning, 18 ticket. All 124 previously specified only the receiver
`Omi - Services Alerting (Telegram)`; actual timing therefore depended on live
Grafana defaults. No contact-point, template, or policy-tree provisioning exists
in the monitoring Helm values. This lane has no Grafana token: live template,
parse mode, timings, contact UID and policy state are **unverified**. Do not
infer a measured delivery reduction from repository counts.

Inventory query (repo only):
```bash
jq -s 'add | {rules:length, severity:(group_by(.labels.severity) |
  map({severity:.[0].labels.severity, count:length})),
  timing:(group_by(.notification_settings) | map({settings:.[0].notification_settings,count:length}))}' \
  backend/charts/monitoring/alerts/*.json
```

## Policy and message

Rules use direct `notification_settings`, bypassing the notification policy tree.
All group by `alertname` (instances, including pods/providers/lanes, batch within
a rule). Critical: wait 30s, group interval 5m, repeat 4h. Warning **and ticket**:
wait 5m, group interval 1h, repeat 24h. This is a per-rule digest, not a global
hourly report: changing groups can notify hourly, a new alertname gets its own
initial notification, and resolved-before-wait groups may never notify. Critical
severity changes retain immediate paging. No severity or evaluation is changed.
The shared contact remains audible: batching reduces interruptions but does not
promise silent warnings. A separate silent contact needs an operator decision
and a secret-bearing contact clone; it is outside this slice.

`telegram.tmpl` is a Grafana Go notification template group. Apply
`telegram-settings.json` to the existing Telegram receiver settings, preserving
bot token, chat ID, thread ID, and resolve notifications. It uses `parse_mode=None`
so `<`, `&`, quotes, and Markdown punctuation are literal. No HTML/Markdown
escaping or truncated entity can break delivery. See [Grafana Telegram guidance](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-telegram/).
Bounded fields and one representative instance keep storms below 4096 characters;
oversized URLs are omitted intact, never truncated into misleading links. Group
counts and the rule link expose all instances. Missing values/labels/links are
explicit. Truncated summary, impact and action prose is marked explicitly; the rule retains
full annotations.
Dashboard additions point to committed component dashboards, not invented panels.

Illustrative before (Grafana default; **not captured live**):
```text
[FIRING:1] Pusher - 4XX error rate is high
Value: B=12.5, C=1
Labels: alertname=..., severity=warning, pod=pusher-abc, ...
Annotations: summary=..., user_impact=..., verification=..., ...
```
After (synthetic compact example):
```text
🚨 Pusher - 5XX error rate is high | live transcription production path
Firing: 3; resolved: 0. First affected instance:
Summary: Elevated Pusher server errors.
Impact: Users may lose live transcription.
Values: map[B:12.5 C:1]
Affected: pod=pusher-abc lane=live provider=modulate
Dashboard/panel: https://monitor.omi.me/d/c758b698-01a0-4b5c-b58c-e81e4ff33ccd
Next: Inspect service readiness and confirm real traffic before rollback.
Rule/all instances: https://monitor.omi.me/alerting/grafana/test/view
Silence: https://monitor.omi.me/alerting/silence/new?alertname=test
```
Warnings/tickets begin `⚠️ DIGEST`. Resolved:
```text
✅ RESOLVED Pusher - 5XX error rate is high | live transcription production path
Recovered: 3 instance(s).
Rule: https://monitor.omi.me/alerting/grafana/test/view
```

## Supervisor rollout (not executed by this lane)

Use the already-authorized provisioning identity through the documented protected
`MONITOR_GRAFANA_TOKEN` path; do not request a new token from David. First export
GET `/api/v1/provisioning/contact-points`, `/templates`, `/policies`, and
`/alert-rules`. Keep only receiver UID/name/type, `disableResolveMessage`, and
allowlisted formatting settings from contact points; never commit chat IDs,
secure settings, bot tokens, or full contact responses. Template/policy exports
establish the real before state. Back up full rule/template state privately for
rollback; policy tree is read-only and not replaced. Abort if the receiver has
multiple Telegram integrations until each integration is reviewed.

With an existing mode-0600 token file, from the repository root:
```bash
set -euo pipefail
GRAFANA_HOST=https://monitor.omi.me
APPLY_NOTIFICATIONS=${APPLY_NOTIFICATIONS:-0} # Default: prepare/review only.
# TOKEN_FILE must already point at the supervisor's protected token file.
AUTH_HEADER=$(mktemp)
chmod 600 "$AUTH_HEADER"
trap 'rm -f "$AUTH_HEADER"' EXIT
{ printf 'Authorization: Bearer '; cat "$TOKEN_FILE"; printf '\n'; } > "$AUTH_HEADER"
NOTIFY=backend/charts/monitoring/notifications
jq -n --rawfile template "$NOTIFY/telegram.tmpl" '{template:$template}' > /tmp/omi-telegram-template.json
if [ "$APPLY_NOTIFICATIONS" = 1 ]; then
curl --fail-with-body -sS -X PUT -H @"$AUTH_HEADER" -H 'Content-Type: application/json' \
  --data-binary @/tmp/omi-telegram-template.json \
  "$GRAFANA_HOST/api/v1/provisioning/templates/omi-telegram" > /dev/null
fi
```
In Grafana Alerting → Contact points → existing Telegram integration, preserve
all secret/destination fields, paste the three settings in `telegram-settings.json`,
and leave resolved messages enabled. Preview and send synthetic critical, warning,
multi-instance and resolved tests to an approved test destination first. Do not
send a synthetic page to the prod room without the operator's approval.

Update **existing live rules only** via provisioning PUT; do not activate the
committed-but-absent/pending Soniox rules. Compare the fleet export first and
stop on divergent queries/labels rather than overwriting live emergency edits.
The following preserves live query/evaluation, paused status, labels and extra
annotations and applies only committed notification metadata. Run the GET/jq
portion and review bodies first. Both blocks default to dry-run; only the authorized
supervisor sets `APPLY_NOTIFICATIONS=1` and reruns them to execute PUTs:
```bash
WORK=$(mktemp -d)
chmod 700 "$WORK"
while IFS= read -r uid; do
  code=$(curl -sS -o "$WORK/live.json" -w '%{http_code}' -H @"$AUTH_HEADER" \
    "$GRAFANA_HOST/api/v1/provisioning/alert-rules/$uid")
  if [ "$code" = 404 ]; then continue; fi
  test "$code" = 200
  jq --arg uid "$uid" --slurpfile desired backend/charts/monitoring/alert-rules.json \
    '($desired[0][] | select(.uid==$uid)) as $r |
     .notification_settings=$r.notification_settings | .annotations += $r.annotations' \
    "$WORK/live.json" > "$WORK/$uid.json"
  if [ "$APPLY_NOTIFICATIONS" = 1 ]; then
  curl --fail-with-body -sS -X PUT -H @"$AUTH_HEADER" -H 'Content-Type: application/json' \
    --data-binary @"$WORK/$uid.json" "$GRAFANA_HOST/api/v1/provisioning/alert-rules/$uid" > /dev/null
  fi
done < <(jq -r '.[].uid' backend/charts/monitoring/alert-rules.json)
python3 backend/scripts/verify_pusher_live_alert_route.py --mode fleet --fail-on gated \
  --grafana-url "$GRAFANA_HOST" --token-file "$TOKEN_FILE"
```
GET each updated rule and compare timing/annotations exactly; GET the template
and preview actual messages. Fleet verification checks query/label drift and receiver existence, not timing/
annotation parity, rendering or real Telegram delivery. Record a real firing/resolved acceptance
receipt and one warning group over its 1h interval. Rollback uses saved rule bodies,
old template body, and prior formatting settings with the same API/UI paths.

**No Helm upgrade or workflow run is needed for this slice.** Helm does not load
these JSON/template exports. The existing metrics-egress workflow imports only its
live-STT/Redis subset; it cannot roll out the full fleet or Telegram template.
Future rule imports inherit the committed settings. This lane did no prod writes,
workflow dispatch, or token read. Savings: no infrastructure-cost change; unchanged
warning groups repeat once/day versus six/day under a hypothetical 4h baseline
(83% fewer repeats). Actual interruption savings need the missing live timing and
notification-history export.
