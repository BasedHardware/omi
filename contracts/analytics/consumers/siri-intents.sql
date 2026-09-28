SELECT event, COUNT(*) FROM events WHERE event = 'Siri Intent Performed' AND app_namespace = :app_namespace AND build_number = :build_number GROUP BY event;
