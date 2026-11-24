SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Subscription Payment Issue Shown',
    'Subscription Payment Issue Update Tapped',
    'Subscription Payment Issue Portal Opened',
    'Subscription Payment Issue Monthly Shown',
    'Subscription Payment Issue Monthly Tapped',
    'Subscription Payment Issue Monthly Switched',
    'Subscription Payment Issue Monthly Failed'
  )
GROUP BY event;
