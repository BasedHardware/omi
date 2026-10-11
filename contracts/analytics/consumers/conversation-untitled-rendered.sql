SELECT event, COUNT(*) FROM events WHERE event = 'Conversation Untitled Rendered' AND app_namespace = :app_namespace AND build_number = :build_number GROUP BY event;
