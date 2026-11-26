-- Project foreground_seconds/capturing_seconds and the SDK's $os from App Foreground Ended
-- properties into this event view (one row each time the app leaves the front).
-- Daily time in the app per person, and the part of it with capture active, by platform.
SELECT day,
       os,
       count(*) AS people,
       sum(foreground_seconds_day) / 3600.0 AS foreground_hours,
       sum(capturing_seconds_day) / 3600.0 AS capturing_foreground_hours,
       avg(foreground_seconds_day) / 60.0 AS foreground_minutes_per_person,
       quantile(0.5)(foreground_seconds_day) / 60.0 AS foreground_minutes_p50,
       quantile(0.9)(foreground_seconds_day) / 60.0 AS foreground_minutes_p90,
       avg(capturing_seconds_day) / 60.0 AS capturing_foreground_minutes_per_person
FROM (
    SELECT toDate(timestamp) AS day,
           os,
           person_id,
           sum(foreground_seconds) AS foreground_seconds_day,
           sum(capturing_seconds) AS capturing_seconds_day
    FROM events
    WHERE app_namespace = :app_namespace AND build_number = :build_number
      AND event = 'App Foreground Ended'
    GROUP BY day, os, person_id
)
GROUP BY day, os;
