-- Presence by release, including devices that report zero pending WALs.
SELECT event, COUNT(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
AND event = 'Mobile Held WAL Backlog'
GROUP BY event;
