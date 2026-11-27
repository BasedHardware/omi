-- PostHog SQL. Set release_at to the UTC release timestamp (YYYY-MM-DD HH:MM:SS)
-- and app_namespace to the released mobile namespace.
-- Each outcome counts people. Sum answered counts within a tenure/plan segment
-- for the denominator of its reason distribution.
WITH survey_events AS (
    SELECT
        event,
        person_id,
        timestamp,
        person.properties.user_created_at AS user_created_at,
        properties.plan AS plan,
        properties.reason AS reason
    FROM events
    WHERE properties.$app_namespace = {variables.app_namespace}
      AND event IN ('Pendant Stop Question Shown', 'Pendant Stop Question Answered', 'Pendant Stop Question Dismissed')
      AND timestamp >= toDateTime({variables.release_at}, 'UTC')
      AND timestamp < toDateTime({variables.release_at}, 'UTC') + INTERVAL 14 DAY
),
answers AS (
    SELECT
        person_id,
        min(timestamp) AS answered_at,
        parseDateTimeBestEffortOrNull(toString(argMin(user_created_at, timestamp))) AS joined_at,
        argMin(plan, timestamp) AS answer_plan,
        argMin(reason, timestamp) AS answer_reason
    FROM survey_events
    WHERE event = 'Pendant Stop Question Answered'
    GROUP BY person_id
)
SELECT
    'answered' AS outcome,
    multiIf(joined_at IS NULL OR joined_at > answered_at, 'unknown',
        answered_at <= joined_at + INTERVAL 30 DAY, '30_days_or_less', 'over_30_days') AS tenure,
    answer_plan AS plan,
    answer_reason AS reason,
    count(*) AS people
FROM answers
GROUP BY tenure, plan, reason
UNION ALL
SELECT
    if(event = 'Pendant Stop Question Shown', 'shown', 'dismissed') AS outcome,
    'all' AS tenure,
    'all' AS plan,
    '' AS reason,
    uniqExact(person_id) AS people
FROM survey_events
WHERE event IN ('Pendant Stop Question Shown', 'Pendant Stop Question Dismissed')
GROUP BY outcome
