-- Offline/PostHog SQL projection: bind one namespace and build; properties carry only the closed channel enum (telegram, imessage).
SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Chat App Connect Started',
    'Chat App Connected',
    'Chat App Disconnected',
    'Chat App Waitlist Joined'
  )
GROUP BY event;
