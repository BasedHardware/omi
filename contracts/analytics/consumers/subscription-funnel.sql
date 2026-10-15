-- Offline/PostHog SQL projection: bind one namespace and build.
-- Closed properties only: source, current_plan, plan, billing_interval, previous_plan, new_plan, change_source, reason, has_details, step.
-- Upgrade Succeeded and Upgrade Cancelled are the property-less presence names.
-- Upgrade Succeeded Attributed is the checkout success that carries tier and interval.
SELECT event, COUNT(*) AS emitted
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event IN (
    'Paywall Opened',
    'Upgrade Plan Selected',
    'Upgrade Succeeded Attributed',
    'Upgrade Succeeded',
    'Upgrade Cancelled',
    'Subscription Plan Changed',
    'Subscription Cancel Flow Started',
    'Subscription Cancel Reason Selected',
    'Subscription Cancel Confirmed',
    'Subscription Cancel Kept Plan',
    'Subscription Cancel Abandoned'
  )
GROUP BY event;
