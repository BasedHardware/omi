-- Presence of the conversation-action signal in one mobile namespace and build. The usage question
-- (which action, from which surface) is answered by breaking this event down by its `action` and
-- `surface` properties in PostHog; the checked projection here only proves the event is emitted.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN ('Conversation Action')
GROUP BY event
ORDER BY event;
