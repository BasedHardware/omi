-- Offline/PostHog SQL projection: the app-version update prompt, not the paywall.
-- Wire names are unchanged so existing presence dashboards keep counting them.
SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Upgrade Modal Dismissed',
    'Upgrade Modal Clicked'
  )
GROUP BY event;
