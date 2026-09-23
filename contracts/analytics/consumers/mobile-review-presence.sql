-- Instrumentation presence only; bind a single mobile namespace and build.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('App Review Opportunity', 'App Review Request Attempted', 'App Review Request Finished')
GROUP BY event
ORDER BY event;
