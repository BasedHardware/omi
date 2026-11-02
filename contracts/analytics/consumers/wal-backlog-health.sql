-- Presence/cohort oracle only; frame and reason metrics live in posthog_query.
SELECT event, COUNT(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
AND event IN ('Pendant Frames Dropped', 'WAL Reconcile Poll Summary')
GROUP BY event;
