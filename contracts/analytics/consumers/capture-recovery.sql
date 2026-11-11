-- Self-healing capture signals per kind and trigger for one namespace/build.
SELECT kind, trigger, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'Capture Recovery Observed'
GROUP BY kind, trigger;
