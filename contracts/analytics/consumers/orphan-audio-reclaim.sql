SELECT event, COUNT(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
AND event = 'Orphan Audio Reclaim' GROUP BY event;
