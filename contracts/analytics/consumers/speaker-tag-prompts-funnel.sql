-- Offline/PostHog SQL projection: bind one namespace and build; properties carry only closed enums, bools and counts.
SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Speaker Tag Prompts Viewed',
    'Speaker Tag Prompt Clip Played',
    'Speaker Tag Prompt Answer Submitted',
    'Speaker Tag Prompts Closed',
    'Voice Profile Setting Toggled'
  )
GROUP BY event;
