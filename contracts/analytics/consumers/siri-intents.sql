SELECT event, COUNT(*) FROM events WHERE event IN ('Siri Intent Performed', 'Siri Ask Omi Performed') AND app_namespace = :app_namespace AND build_number = :build_number GROUP BY event;
