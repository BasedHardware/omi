SELECT event, count(*) FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Live Preview Engine', 'Live Preview First Word', 'Live Preview Session Ended', 'Live Preview Not Requested', 'Live Preview Verdict', 'Live Preview Notes')
GROUP BY event;
