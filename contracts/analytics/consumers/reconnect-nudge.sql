-- Reconnect row presence for one namespace and build. Join taps to later device sessions per
-- person for recovery; this query only proves the three events arrive.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Reconnect Nudge Shown', 'Reconnect Nudge Tapped', 'Reconnect Nudge Dismissed')
GROUP BY event;
