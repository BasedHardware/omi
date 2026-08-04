# PostHog telemetry regression alerts

These alerts detect discontinuities in load-bearing product events. They are
PostHog project configuration, not application code.

## Ownership

- Project: Omi, US Cloud (`302298`)
- Severity: ticket; these weekly product signals do not page
- Notification: subscribe the product telemetry owner and the team's telemetry
  notification channel
- Response: compare the first bad week with releases and analytics call-site
  changes, then confirm the emitter in a development build before changing the
  alert

Production PostHog changes require their own explicit approval. This repository
has authenticated read-only HogQL access through
`web/admin/lib/posthog.ts`, using `POSTHOG_PERSONAL_API_KEY`,
`POSTHOG_PROJECT_ID`, and `POSTHOG_HOST`. It has no alert or dashboard
provisioning lane. Do not add one only for these alerts.

## Weekly volume contract

Create one **Trends** insight named **Telemetry health: weekly unique people**.
Add one event series for each event below, set every series to **Unique users**,
use a **weekly** interval and a line chart, and save it:

| Event |
|---|
| `Device Connected` |
| `Device Disconnected` |
| `Device Paired` |
| `Get Omi Device Clicked` |
| `Sign In Completed` |
| `Memory Created` |
| `Chat Message Sent` |
| `Upgrade Succeeded` |
| `Account Deletion Wipe Completed` |

For each series, create this alert:

| Field | Value |
|---|---|
| Name | `Telemetry WoW -50% — <event>` |
| Series | The matching event series |
| Condition | **decreases by**, percentage threshold **50%** |
| Check frequency | **Weekly** |
| Check ongoing period | **Off** |
| Quiet hours | None |
| Destinations | Subscribed owner plus the telemetry notification channel |

The contract is a 50% or larger fall in unique people between the two most
recent completed weeks. Keeping **Check ongoing period** off is required:
otherwise a partial current week is compared with a complete prior week and
creates a predictable false alert.

A relative alert needs two completed periods. For a newly introduced event,
verify its first two weeks with the query below, then confirm the alert is
enabled. Do not weaken the shared threshold for a low-volume event; triage its
occasional ticket instead.

## Connection balance contract

Create a **SQL** insight named
**Telemetry health: Device Connected / Disconnected ratio** with this HogQL:

```sql
SELECT
    toStartOfWeek(timestamp) AS week,
    round(
        uniqIf(COALESCE(person_id, distinct_id), event = 'Device Connected')
        / nullIf(
            uniqIf(COALESCE(person_id, distinct_id), event = 'Device Disconnected'),
            0
        ),
        3
    ) AS ratio
FROM events
WHERE event IN ('Device Connected', 'Device Disconnected')
  AND timestamp >= now() - INTERVAL 13 WEEK
  AND timestamp < toStartOfWeek(now())
GROUP BY week
ORDER BY week
```

Create one alert on the `ratio` column:

| Field | Value |
|---|---|
| Name | `Telemetry ratio low — Device Connected / Disconnected` |
| Evaluation | Last row |
| Condition | **has value**, less than **0.7** |
| Check frequency | **Weekly** |
| Check ongoing period | **Off** |
| Quiet hours | None |
| Destinations | Subscribed owner plus the telemetry notification channel |

The query excludes the current partial week. A zero disconnect denominator
returns `NULL`; the `Device Disconnected` volume alert owns that failure. A
one-sided connection-emission regression returns a low ratio and triggers this
alert even when overall traffic changes.

## Setup and verification

1. In PostHog, open **Product analytics → Insights → New insight** and create
   the two saved insights above.
2. On each insight, open **Actions → Alerts → New alert** and apply the exact
   contract above.
3. Confirm Product analytics → **Alerts** contains nine enabled
   `Telemetry WoW -50%` alerts and one enabled ratio alert.
4. Run the two read-only queries below. The volume query must return every
   expected live event; the ratio query must match the SQL insight's last row.
5. Record the insight and alert links in the event dictionary. Re-check alert
   status after editing an insight because PostHog disables alerts whose series
   or query becomes incompatible.

Weekly volume verification:

```sql
SELECT
    toStartOfWeek(timestamp) AS week,
    event,
    uniq(COALESCE(person_id, distinct_id)) AS people
FROM events
WHERE event IN (
    'Device Connected',
    'Device Disconnected',
    'Device Paired',
    'Get Omi Device Clicked',
    'Sign In Completed',
    'Memory Created',
    'Chat Message Sent',
    'Upgrade Succeeded',
    'Account Deletion Wipe Completed'
)
  AND timestamp >= now() - INTERVAL 13 WEEK
  AND timestamp < toStartOfWeek(now())
GROUP BY week, event
ORDER BY week, event
LIMIT 1000
```

Read-only alert inventory (the personal API key needs `alert:read`):

```bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer $POSTHOG_PERSONAL_API_KEY" \
  "${POSTHOG_HOST%/}/api/environments/$POSTHOG_PROJECT_ID/alerts/?limit=100"
```

The read-only acceptance result is ten enabled alerts with the names and
conditions above. A missing `alert:read` scope is an inspection failure, not a
reason to broaden the admin dashboard's production token without approval.

PostHog references: [alert setup and completed-period behavior][alerts] and
the [`alert:read` inventory API][alerts-api].

[alerts]: https://posthog.com/docs/alerts
[alerts-api]: https://posthog.com/docs/api/alerts
