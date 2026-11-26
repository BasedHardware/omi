# Pendant drop-off telemetry

When someone stops capturing, these fields tell a pendant that failed or became unusable apart from one that
was put down. They are properties on `Mobile Device Health Daily` (`schema_version` 3), computed by
[`DeviceDropoffSignals`](../lib/utils/analytics/device_dropoff_signals.dart) from the native diagnostics
snapshot the daily rollup already reads. There is no new event, native call, scan or BLE traffic.

Kill switch: PostHog flag `device_dropoff_telemetry_off`. True omits every field below and restores
`schema_version` 2. Absent, false or unreadable keeps them on.

## Why the older fields could not answer this

- `charge_events` needs the firmware Diagnostics characteristic (charging bit), which ships from firmware
  3.0.24. The fleet runs 3.0.21, so it reads 0. `charge_inferred_events` infers charging from the level.
- `lost_audio_seconds` is time without a link. It is kept as is. `connected_seconds`,
  `disconnected_seconds` and `connected_no_audio_seconds` split the day.
- `connection_timeout` is the reason for nearly every loss: firmware power-off and the battery-critical
  shutdown cut power without a link terminate, so the phone sees a supervision timeout, the same as walking
  out of range. `gap_cause` uses RSSI at loss and the last battery level instead.

## Gap

A gap is a `disconnect` row whose next connection starts at least 30 minutes later, or has not started by the
snapshot time. Every day's event describes the **most recent gap that started before the day's end**, so a
fully disconnected day still carries the cause of the gap the device is in.

`gap_cause` rules, first match wins:

| Value | Rule |
|---|---|
| `manual` | The user disconnected. |
| `pairing_lost` | `pairing_lost`, `paired_to_another_phone` or `link_key_mismatch`. |
| `phone_side` | `bluetooth_off` or `app_closed`. |
| `battery_flat` | Last battery sample at most 60 min before the loss was ≤ 5% and not charging. |
| `out_of_range` | RSSI trend `fading`, or an RSSI sample at most 30 s old ≤ −85 dBm. |
| `power_off` | An RSSI sample at most 30 s old ≥ −75 dBm: an abrupt loss at strong signal (powered off, reset or crashed). |
| `unknown` | Anything else, including no recent RSSI. |

## Fields

| Field | Meaning |
|---|---|
| `connected_seconds`, `disconnected_seconds` | The day split by link state (local day). |
| `short_sessions` | Links that dropped within 30 s of connecting ("keeps disconnecting seconds after connecting"). A put-down pendant does not reconnect at all. |
| `connected_no_audio_seconds`, `connected_no_audio_sessions` | Time and count of link sessions of at least 60 s that delivered zero audio packets. Only reported for a device that has delivered audio in retained history. |
| `audio_packets_per_connected_minute` | Audio packets received per connected minute; null under one connected minute. A mic that stops mid-session lowers it. |
| `long_gaps`, `long_gaps_by_cause` | Gaps that started this day, and their causes. |
| `gap_cause` | See above. |
| `gap_age_hours` | Hours from the gap start to the day's end. |
| `gap_minutes` | Gap length up to its reconnect or the day's end. |
| `gap_open_at_day_end` | No reconnect by the day's end. |
| `gap_battery_level`, `gap_battery_age_min`, `gap_battery_charging` | Last battery sample before the loss, its age, and the charging bit (null unless firmware reports it). |
| `gap_last_rssi`, `gap_rssi_age_s`, `gap_rssi_trend` | RSSI evidence at the loss. |
| `gap_short_sessions_24h` | Short sessions in the 24 h before the gap: a gap that ends a run of connect-then-drop links. |
| `gap_fail_to_connect` | Connection attempts inside the gap that reached the device and failed. Zero with the gap open means no attempt reached it. |
| `gap_saved_reconnect_enabled`, `gap_reconnect_suppressed` | iOS only, only while the gap is still open at the snapshot: whether the app is still trying to reconnect. |
| `gap_scan_windows`, `gap_advert_sightings` | iOS only: reconnect scans inside the gap and how often they saw this pendant advertising. Null when the 24-hour native log no longer reaches back to the gap start. Android reconnects with a passive OS scan and logs none, so the fields are absent there. |
| `charge_inferred_events` | Non-decreasing battery runs that gained at least 5 points, counted on the day they crossed it. A run may span a disconnection (charged off the link). |
| `battery_min_level`, `battery_max_level` | Day range of battery samples. |
| `battery_low_seconds` | Time the level sat at or below 5% (samples at most 2 h apart): "stuck at 1% then shuts off", "won't charge" when it recurs without `charge_inferred_events`. |
| `battery_erratic_steps` | Samples at most 10 min apart that differ by 20 points or more, in either direction ("erratic battery reading"). A plug-in jump can also count. |

## Cost

No new events. The daily event stays at about 0.75 per active pendant user per day (26,131 events from
4,991 users in the 7 days to 2026-11-26, keep-listed at 100%). It gains up to 29 properties (25 on Android), about +0.6 KB per
user-day. PostHog bills per event, so there is no added event cost.

## Separating the two kinds of drop-off

A stop is the first day with `connected_seconds = 0` after at least 5 connected days in the previous 14, with
the next 2 days also at zero. The stop day's gap fields describe the stop; the 3 days before it show whether
audio, battery or resets were already failing.

```sql
WITH per_day AS (
  SELECT person_id,
         dateDiff('day', toDate('2020-01-01'), toDate(properties.day)) AS d,
         max(toFloat(properties.connected_seconds)) AS conn_s,
         max(toFloat(properties.connected_no_audio_seconds)) AS silent_s,
         argMax(toString(properties.gap_cause), timestamp) AS gap_cause,
         argMax(toFloat(properties.gap_battery_level), timestamp) AS gap_batt,
         max(toFloat(properties.gap_fail_to_connect)) AS gap_fails,
         max(toFloat(properties.gap_advert_sightings)) AS gap_seen,
         max(toFloat(properties.cliff_count)) AS cliffs,
         max(toFloat(properties.short_sessions)) AS short_n,
         max(toFloat(properties.battery_low_seconds)) AS low_s,
         max(toFloat(properties.battery_erratic_steps)) AS erratic,
         max(if(toString(properties.device_resets_by_reason) NOT IN ('', '{}', 'null'), 1, 0)) AS resets,
         argMax(toFloat(properties.gap_short_sessions_24h), timestamp) AS gap_short
  FROM events
  WHERE event = 'Mobile Device Health Daily'
    AND toInt(properties.schema_version) >= 3
    AND timestamp >= now() - INTERVAL 60 DAY
  GROUP BY person_id, d
),
per_person AS (
  SELECT person_id,
         arraySort(x -> x.1, groupArray((d, conn_s, silent_s, gap_cause, gap_batt, gap_fails, gap_seen, cliffs,
                                         short_n, low_s, erratic, resets, gap_short))) AS days
  FROM per_day
  GROUP BY person_id
),
stops AS (
  SELECT person_id, days,
         arrayFirst(x -> x.2 = 0
             AND arrayCount(y -> y.1 >= x.1 - 14 AND y.1 < x.1 AND y.2 > 0, days) >= 5
             AND arrayCount(y -> y.1 >= x.1 AND y.1 <= x.1 + 2 AND y.2 > 0, days) = 0
             AND x.1 + 2 <= dateDiff('day', toDate('2020-01-01'), today()) - 1,
           days) AS stop
  FROM per_person
),
classified AS (
  SELECT stop,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 < stop.1, coalesce(y.3, 0), 0), days)) AS silent_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 < stop.1, coalesce(y.2, 0), 0), days)) AS conn_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 <= stop.1, coalesce(y.8, 0), 0), days)) AS cliffs_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 <= stop.1, coalesce(y.9, 0), 0), days)) AS short_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 <= stop.1, coalesce(y.10, 0), 0), days)) AS low_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 3 AND y.1 <= stop.1, coalesce(y.11, 0), 0), days)) AS erratic_before,
         arraySum(arrayMap(y -> if(y.1 >= stop.1 - 14 AND y.1 <= stop.1, coalesce(y.12, 0), 0), days)) AS reset_days
  FROM stops
  WHERE stop.1 > 0
)
SELECT multiIf(
         stop.4 = 'battery_flat' OR stop.6 > 0 OR stop.7 > 0 OR stop.13 >= 3
           OR (conn_before > 0 AND silent_before > 0.5 * conn_before)
           OR cliffs_before > 0 OR short_before >= 10 OR low_before >= 3600 OR erratic_before > 0
           OR reset_days > 0, 'hardware',
         stop.4 IN ('out_of_range', 'power_off', 'manual') AND stop.5 > 20, 'put_down',
         'unclassified') AS dropoff_kind,
       stop.4 AS gap_cause,
       count() AS people
FROM classified
GROUP BY dropoff_kind, gap_cause
ORDER BY dropoff_kind, people DESC
```

`hardware` covers a flat battery, failed reconnect attempts, the pendant seen advertising without connecting,
mostly silent connected time, short-session churn (at least 3 in the 24 h before the gap, or 10 in the 3 days
before the stop), an hour or more stuck at ≤ 5%, an erratic or cliff battery step, or any firmware reset in the
14 days before (`device_resets_by_reason`, mostly `RESET_LOW_POWER_WAKE`, which may itself mean a flat battery;
only 3.0.24+ reports it, about 0.1% of daily rows today). `put_down` is a clean loss (out of range,
powered off or manual) with more than 20% battery left. `unclassified` keeps the unknown share visible.
Restrict `per_day` to a cohort (cancellers, a churn study's stoppers) with a `person_id IN (...)` subquery.

## Known blind spot

Support-reported hardware faults were mostly invisible to the schema 2 fields: of 25 cancellers who reported a
hardware problem to support in the 90 days before cancelling and had telemetry, 18 had no failure or reset event
in the 14 days before cancelling, and their connected fraction and failure-event rate matched cancellers who never
contacted support. The schema 3 short-session, stuck-low and erratic-battery fields target the reported
symptoms (won't charge, stuck at 1% then off, disconnects seconds after connecting, erratic reading). Once schema
3 has a month of data, measure recall against that support-reported group before trusting a `put_down` share.
A firmware freeze with a solid LED that needs a cable reset is still invisible until the firmware reports it.

## Firmware follow-up (not implemented)

1. Ship the 3.0.24+ Diagnostics characteristic to the fleet. It makes `charge_events`,
   `charge_pin_edges_max`, reset causes and the battery charging bit real.
2. In `turnoff_all()`, terminate the link before `sys_poweroff()` with a distinct HCI reason for the button
   and battery-critical paths. The phone would then report `remote_device_terminated` with a code instead of
   a supervision timeout.
3. Persist the last shutdown cause (button, battery critical, brownout) and expose it in the Diagnostics
   characteristic, so the next connection explains why the pendant went silent.
4. Record a watchdog or hang marker (and the LED state at the time) that survives the cable reset, so a
   "solid blue, needs a cable reset" freeze on 3.0.21-class firmware reports itself on the next connection.
