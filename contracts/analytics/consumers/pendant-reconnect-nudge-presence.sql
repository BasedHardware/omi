SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Pendant Reconnect Nudge Eligible',
    'Pendant Reconnect Nudge Shown',
    'Pendant Reconnect Nudge Tapped',
    'Pendant Reconnect Nudge Dismissed'
  )
GROUP BY event;
