SELECT event, COUNT(*) FROM events WHERE app_namespace = :app_namespace AND build_number = :build_number AND event = 'Native Custody Observed' GROUP BY event;
