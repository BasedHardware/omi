import { EXCLUSIONS_SQL, sqlTime, shiftDay } from "./qualified-activity";

export const MCP_MARKER = "MCP Tool Use Succeeded";
export const MCP_MARKER_STATUS_ROW = "__mcp_marker_status";
export const MCP_MARKER_MISSING = "MCP marker not deployed";
export const MCP_ACTIVITY_VERSION = "qualified-v2-2026-10-15-mcp-schema2";
export const MCP_DAILY_MIN_SUCCESSES = 2;
// Use the same projection for events and event-shaped literal integration tests.
// HogQL's properties.foo shorthand only resolves on the physical events table;
// explicit JSON access also works on a literal properties object.
export const MCP_SUCCESS_SELECT = `coalesce(toString(person_id),distinct_id) actor,timestamp,
  coalesce(nullIf(JSONExtractString(properties,'client'),''),'unknown') client,
  coalesce(nullIf(JSONExtractString(properties,'tool'),''),'unknown') tool,
  JSONExtractString(properties,'initiator') initiator`;
// Bounded daily approximation of the threshold evidence's cadence screen.
// Multi-day / separated-burst regularity is deferred, rather than inferred from
// client labels. Client/person/day statistics remain inside the aggregate query.
export const MCP_CADENCE = {
  calls: 10,
  positiveGaps: 8,
  spanSeconds: 7200,
  dominantShare: 0.8,
  minGapSeconds: 60,
  maxGapSeconds: 86400,
  maxCv: 0.15,
} as const;

export const MCP_ROLLUP_EVENT = "MCP Daily Activity";
export const MCP_ROLLUP_SCHEMA_VERSION = 1;
const UTC_DAY_OF = (at: string) => `intDiv(toUnixTimestamp(${at}),86400)`;
const prop = (name: string) => `JSONExtractString(properties,'${name}')`;
const int = (name: string) => `JSONExtractInt(properties,'${name}')`;
const num = (name: string) => `toFloat(${int(name)})`;
type McpSource = "both" | "raw" | "rollup";

/** Raw per-success rows plus the server's daily rollup snapshots (SCA-3665).
 * `mcp_marker` counts either kind, so the marker survives the raw stream going
 * off. Snapshots for day D arrive up to a flush after D ends, so they are read
 * one day past `end` and filtered by their own UTC day. */
export function mcpMarkerCte(
  start: Date,
  end: Date,
  observationDays = 30,
  source: McpSource = "both"
) {
  // A quiet day must show zero once a v2 marker has appeared in recent history.
  const observedStart = new Date(
    Math.min(start.getTime(), shiftDay(end, -observationDays).getTime())
  );
  return `mcp_raw AS (
    SELECT ${MCP_SUCCESS_SELECT}
    FROM events WHERE event='${MCP_MARKER}'${
    source === "rollup" ? " AND false" : ""
  } AND timestamp >= ${sqlTime(observedStart)} AND timestamp < ${sqlTime(end)}
      AND ${int("schema_version")}=2 AND ${EXCLUSIONS_SQL}
  ),
  mcp_rollup_raw AS (
    SELECT coalesce(toString(person_id),distinct_id) actor,timestamp,
      coalesce(nullIf(${prop("client")},''),'unknown') client,
      ${UTC_DAY_OF(
        `toDateTime(concat(${prop("utc_day")},' 00:00:00'),'UTC')`
      )} utc_day,
      ${num("raw_calls")} raw_calls,${num("calls")} calls,${num("span_s")} span,
      ${num("positive_gaps")} gaps,${num("sum_gap_s")} sum_gap,${num(
    "sum_gap_sq_s"
  )} sum_gap_sq,
      ${num("dominant_tool_calls")} dominant,
      toDateTime(${int("last_call_s")}) latest
    FROM events WHERE event='${MCP_ROLLUP_EVENT}'${
    source === "raw" ? " AND false" : ""
  } AND timestamp >= ${sqlTime(observedStart)} AND timestamp < ${sqlTime(
    shiftDay(end, 1)
  )}
      AND ${int("schema_version")}=${MCP_ROLLUP_SCHEMA_VERSION} AND ${int(
    "raw_calls"
  )} > 0 AND ${EXCLUSIONS_SQL}
  ),
  mcp_marker AS (SELECT actor FROM mcp_raw UNION ALL SELECT actor FROM mcp_rollup_raw
    WHERE utc_day >= ${UTC_DAY_OF(
      sqlTime(observedStart)
    )} AND utc_day < ${UTC_DAY_OF(sqlTime(end))})`;
}

/** Per actor/client/UTC day cadence statistics from whichever source saw more
 * qualifying calls, raw rows on a tie: raw is complete while the raw stream is
 * on, and the rollup's largest snapshot covers the day the stream is switched
 * off mid-day and every day after. The rollup accumulates the same counts,
 * positive gaps, gap sums and dominant tool as the raw SQL below; its day comes
 * from the success time and its gaps from Redis TIME (one ordered clock), so
 * gaps can differ from the raw event clock by queue delay. */
export function mcpActivityCtes(
  start: Date,
  end: Date,
  observationDays = 30,
  source: McpSource = "both"
) {
  return `${mcpMarkerCte(start, end, observationDays, source)},
  mcp_eligible AS (SELECT *,intDiv(toUnixTimestamp(timestamp),86400) AS utc_day FROM mcp_raw WHERE initiator IN ('user','unknown')),
  mcp_ordered AS (SELECT actor,timestamp,client,tool,initiator,utc_day,
    lagInFrame(timestamp,1,timestamp) OVER (PARTITION BY actor,client,utc_day ORDER BY timestamp) previous_at
    FROM mcp_eligible),
  mcp_calls AS (SELECT *,dateDiff('second',previous_at,timestamp) gap FROM mcp_ordered),
  mcp_tools AS (SELECT actor,client,utc_day,tool,count() n FROM mcp_calls GROUP BY actor,client,utc_day,tool),
  mcp_dominance AS (SELECT actor,client,utc_day,max(n) dominant FROM mcp_tools GROUP BY actor,client,utc_day),
  mcp_raw_stats AS (SELECT s.actor actor,s.client client,s.utc_day utc_day,calls,span,gaps,sum_gap,sum_gap_sq,
    toFloat(d.dominant) dominant,latest FROM (SELECT actor,client,utc_day,toFloat(count()) calls,
    toFloat(dateDiff('second',min(timestamp),max(timestamp))) span,
    toFloat(countIf(gap>0)) gaps,toFloat(sumIf(gap,gap>0)) sum_gap,toFloat(sumIf(gap*gap,gap>0)) sum_gap_sq,
    max(timestamp) latest FROM mcp_calls GROUP BY actor,client,utc_day) s
    JOIN mcp_dominance d ON s.actor=d.actor AND s.client=d.client AND s.utc_day=d.utc_day),
  mcp_roll_stats AS (SELECT actor,client,utc_day,
    argMax(calls,tuple(raw_calls,timestamp)) calls,argMax(span,tuple(raw_calls,timestamp)) span,
    argMax(gaps,tuple(raw_calls,timestamp)) gaps,argMax(sum_gap,tuple(raw_calls,timestamp)) sum_gap,
    argMax(sum_gap_sq,tuple(raw_calls,timestamp)) sum_gap_sq,argMax(dominant,tuple(raw_calls,timestamp)) dominant,
    argMax(latest,tuple(raw_calls,timestamp)) latest
    FROM mcp_rollup_raw GROUP BY actor,client,utc_day),
  mcp_stream_union AS (SELECT actor,client,utc_day,calls c,span sp,gaps g,sum_gap sg,sum_gap_sq sq,dominant dm,latest lt,1 prio FROM mcp_raw_stats
    UNION ALL SELECT actor,client,utc_day,calls c,span sp,gaps g,sum_gap sg,sum_gap_sq sq,dominant dm,latest lt,0 prio FROM mcp_roll_stats),
  mcp_stream_stats AS (SELECT actor,client,utc_day,argMax(c,tuple(c,prio)) calls,argMax(sp,tuple(c,prio)) span,argMax(g,tuple(c,prio)) gaps,
    if(argMax(g,tuple(c,prio))>0,argMax(sg,tuple(c,prio))/argMax(g,tuple(c,prio)),0) mean_gap,
    if(argMax(g,tuple(c,prio))>0,argMax(sq,tuple(c,prio))/argMax(g,tuple(c,prio)),0) mean_square_gap,
    argMax(dm,tuple(c,prio)) dominant,argMax(lt,tuple(c,prio)) latest
    FROM mcp_stream_union GROUP BY actor,client,utc_day),
  mcp_streams AS (SELECT actor,client,utc_day,calls,latest,
    (calls>=${MCP_CADENCE.calls} AND gaps>=${
    MCP_CADENCE.positiveGaps
  } AND span>=${MCP_CADENCE.spanSeconds}
     AND dominant>=calls*${MCP_CADENCE.dominantShare}
     AND mean_gap>=${MCP_CADENCE.minGapSeconds} AND mean_gap<=${
    MCP_CADENCE.maxGapSeconds
  }
     AND sqrt(greatest(0,mean_square_gap-mean_gap*mean_gap))/mean_gap<=${
       MCP_CADENCE.maxCv
     }) unattended
    FROM mcp_stream_stats),
  mcp_days AS (SELECT actor,utc_day,max(latest) latest
    FROM mcp_streams WHERE NOT unattended AND utc_day >= ${UTC_DAY_OF(
      sqlTime(start)
    )} AND utc_day < ${UTC_DAY_OF(sqlTime(end))}
    GROUP BY actor,utc_day HAVING sum(calls)>=${MCP_DAILY_MIN_SUCCESSES})`;
}

/** Release check for one full UTC day. Each count comes from one source only.
 * Compare eligible calls and qualified actors; require observed inputs on both
 * sides so an empty rollup does not pass on a quiet day. */
export function mcpDailyReconciliationQuery(
  day: Date,
  source: Exclude<McpSource, "both">
) {
  return `WITH ${mcpActivityCtes(day, shiftDay(day, 1), 1, source)}
    SELECT (SELECT count() FROM mcp_marker) marker_rows,
      (SELECT count() FROM mcp_days) qualified_actors,
      (SELECT sum(calls) FROM mcp_streams WHERE utc_day=${UTC_DAY_OF(
        sqlTime(day)
      )}) eligible_calls`;
}
