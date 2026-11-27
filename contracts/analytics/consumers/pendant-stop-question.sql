-- PostHog SQL. Set release_at to the UTC release timestamp (YYYY-MM-DD HH:MM:SS)
-- and app_namespace to the released mobile namespace.
-- Answered rows count each person's first response. Exclude note_only when
-- calculating the distribution among people who selected a reason.
WITH readback_parameters AS (
    SELECT
        toUnixTimestamp64Milli(toDateTime64({variables.release_at}, 3, 'UTC')) AS release_ms,
        {variables.app_namespace} AS app_namespace
),
projected_events AS (
    SELECT
        event,
        person_id,
        toString(uuid) AS event_id,
        toUnixTimestamp64Milli(timestamp) AS event_ms,
        toUnixTimestamp64Milli(parseDateTime64BestEffortOrNull(toString(person.properties.user_created_at))) AS joined_ms,
        properties.$app_namespace AS app_namespace,
        properties.plan AS plan,
        properties.reason AS reason
    FROM events
    WHERE event IN ('Pendant Stop Question Shown', 'Pendant Stop Question Answered', 'Pendant Stop Question Dismissed')
),
-- Offline-testable outcomes
survey_events AS (
    SELECT e.*
    FROM projected_events AS e
    CROSS JOIN readback_parameters AS p
    WHERE e.app_namespace = p.app_namespace
      AND e.event_ms >= p.release_ms AND e.event_ms < p.release_ms + 1209600000
),
answers AS (
    SELECT
        event_ms,
        joined_ms,
        plan,
        reason,
        row_number() OVER (PARTITION BY person_id ORDER BY event_ms, event_id) AS response_order
    FROM survey_events
    WHERE event = 'Pendant Stop Question Answered'
)
SELECT
    'answered' AS outcome,
    CASE
        WHEN joined_ms IS NULL OR joined_ms > event_ms THEN 'unknown'
        WHEN event_ms - joined_ms <= 2592000000 THEN '30_days_or_less'
        ELSE 'over_30_days'
    END AS tenure,
    plan,
    reason,
    count(*) AS people
FROM answers
WHERE response_order = 1
GROUP BY tenure, plan, reason
UNION ALL
SELECT
    CASE WHEN event = 'Pendant Stop Question Shown' THEN 'shown' ELSE 'dismissed' END AS outcome,
    'all' AS tenure,
    'all' AS plan,
    '' AS reason,
    count(DISTINCT person_id) AS people
FROM survey_events
WHERE event IN ('Pendant Stop Question Shown', 'Pendant Stop Question Dismissed')
GROUP BY outcome
