SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Subscription Payment Issue Shown',
    'Subscription Payment Issue Update Tapped',
    'Subscription Payment Issue Portal Opened'
  )
GROUP BY event;
