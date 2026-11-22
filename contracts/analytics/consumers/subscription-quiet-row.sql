SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Subscription Quiet Row Shown',
    'Subscription Quiet Row Tapped'
  )
GROUP BY event;
