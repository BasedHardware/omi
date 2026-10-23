SELECT event, count(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'Capture Recovery Observed'
GROUP BY event;
