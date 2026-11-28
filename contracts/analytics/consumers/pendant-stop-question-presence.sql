SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Pendant Stop Question Shown', 'Pendant Stop Question Answered', 'Pendant Stop Question Dismissed')
GROUP BY event;
