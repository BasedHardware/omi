-- Offline/PostHog SQL projection: bind one namespace and build; never infer identity from person properties.
SELECT event, count(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Recording Produced No Conversation',
    'Onboarding Welcome Shown',
    'Onboarding Get Started Tapped',
    'Sign In Started',
    'Sign In Failed',
    'Onboarding Permission Result',
    'Device Pairing Blocked',
    'Device Scan Empty',
    'Device Connect Failed',
    'Device Connect Failure Shown'
  )
GROUP BY event ORDER BY event;
