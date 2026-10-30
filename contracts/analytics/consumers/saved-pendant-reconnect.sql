-- Project trigger/result from Saved Pendant Reconnect properties into this event view.
-- Each owner emits attempted once per outage, preserving a connected terminal outcome.
SELECT CASE WHEN trigger = 'native_retry' THEN 'native' ELSE 'dart' END AS owner,
       SUM(CASE WHEN result = 'attempted' THEN 1 ELSE 0 END) AS attempted,
       SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) AS connected,
       1.0 * SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END)
         / NULLIF(SUM(CASE WHEN result = 'attempted' THEN 1 ELSE 0 END), 0) AS recovery_rate
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'Saved Pendant Reconnect'
GROUP BY owner;
