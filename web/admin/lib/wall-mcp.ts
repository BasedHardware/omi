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

export function mcpMarkerCte(start: Date, end: Date, observationDays = 30) {
  // A quiet day must show zero once a v2 marker has appeared in recent history.
  const observedStart = new Date(
    Math.min(start.getTime(), shiftDay(end, -observationDays).getTime())
  );
  return `mcp_raw AS (
    SELECT ${MCP_SUCCESS_SELECT}
    FROM events WHERE event='${MCP_MARKER}' AND timestamp >= ${sqlTime(
    observedStart
  )} AND timestamp < ${sqlTime(end)}
      AND toIntOrZero(toString(properties.schema_version))=2 AND ${EXCLUSIONS_SQL}
  )`;
}

export function mcpActivityCtes(start: Date, end: Date, observationDays = 30) {
  return `${mcpMarkerCte(start, end, observationDays)},
  mcp_eligible AS (SELECT *,intDiv(toUnixTimestamp(timestamp),86400) AS utc_day FROM mcp_raw WHERE initiator IN ('user','unknown')),
  mcp_ordered AS (SELECT actor,timestamp,client,tool,initiator,utc_day,
    lagInFrame(timestamp,1,timestamp) OVER (PARTITION BY actor,client,utc_day ORDER BY timestamp) previous_at
    FROM mcp_eligible),
  mcp_calls AS (SELECT *,dateDiff('second',previous_at,timestamp) gap FROM mcp_ordered),
  mcp_tools AS (SELECT actor,client,utc_day,tool,count() n FROM mcp_calls GROUP BY actor,client,utc_day,tool),
  mcp_dominance AS (SELECT actor,client,utc_day,max(n) dominant FROM mcp_tools GROUP BY actor,client,utc_day),
  mcp_stream_stats AS (SELECT actor,client,utc_day,count() calls,
    dateDiff('second',min(timestamp),max(timestamp)) span,
    countIf(gap>0) gaps,avgIf(gap,gap>0) mean_gap,
    avgIf(gap*gap,gap>0) mean_square_gap
    FROM mcp_calls GROUP BY actor,client,utc_day),
  mcp_streams AS (SELECT s.actor,s.client,s.utc_day,
    (calls>=${MCP_CADENCE.calls} AND gaps>=${
    MCP_CADENCE.positiveGaps
  } AND span>=${MCP_CADENCE.spanSeconds}
     AND d.dominant>=calls*${MCP_CADENCE.dominantShare}
     AND mean_gap>=${MCP_CADENCE.minGapSeconds} AND mean_gap<=${
    MCP_CADENCE.maxGapSeconds
  }
     AND sqrt(greatest(0,mean_square_gap-mean_gap*mean_gap))/mean_gap<=${
       MCP_CADENCE.maxCv
     }) unattended
    FROM mcp_stream_stats s JOIN mcp_dominance d ON s.actor=d.actor AND s.client=d.client AND s.utc_day=d.utc_day),
  mcp_days AS (SELECT c.actor,c.utc_day,max(c.timestamp) latest
    FROM mcp_calls c JOIN mcp_streams s ON c.actor=s.actor AND c.client=s.client AND c.utc_day=s.utc_day
    WHERE NOT s.unattended AND c.timestamp >= ${sqlTime(start)}
    GROUP BY c.actor,c.utc_day HAVING count()>=${MCP_DAILY_MIN_SUCCESSES})`;
}
