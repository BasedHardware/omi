SELECT event, COUNT(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
AND event = 'WAL Upload Refused' GROUP BY event;
