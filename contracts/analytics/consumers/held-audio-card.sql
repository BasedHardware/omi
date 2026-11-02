-- Offline/PostHog SQL projection: held-recordings card exposure and taps.
-- Lift is Upgrade taps per card seen, variant=personal against variant=holdout.
SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Held Audio Card Seen',
    'Held Audio Upgrade Tapped',
    'Held Audio Process Tapped'
  )
GROUP BY event;
