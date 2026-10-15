SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Guided Intro Payoff Shown', 'Guided Intro Payoff Continued')
GROUP BY event
ORDER BY event;
