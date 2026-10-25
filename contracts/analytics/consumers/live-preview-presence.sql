SELECT event, count(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Live Preview Engine', 'Live Preview First Word', 'Live Preview Session Ended')
GROUP BY event;
