SELECT event, count(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'Saved Pendant Reconnect'
GROUP BY event;
