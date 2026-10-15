import { mcpActivityCtes, MCP_MARKER_STATUS_ROW } from "./wall-mcp";
import { WallSourceError } from "./wall-source-error";
import { withRowLimit } from "./posthog";
import {
  EXCLUSIONS_SQL,
  PLATFORM_SQL,
  FOREGROUND_SQL,
  SAVED_CAPTURE_SQL,
  CAPTURE_TIME_SQL,
  PLATFORM_RANK_SQL,
  QUALIFIED_EVENT_NAMES,
  sqlTime,
  shiftDay,
} from "./qualified-activity";

export type AggregateRows = unknown[][] & { sourceRefreshedAt?: string | null };
export type Query = (sql: string) => Promise<AggregateRows>;
const ACTOR = "coalesce(toString(person_id),distinct_id)";

function raw(start: Date, end: Date, cohort = "") {
  return `raw AS (SELECT ${ACTOR} actor,person.created_at anchor,event,timestamp,properties,${PLATFORM_SQL} p
    FROM events WHERE timestamp >= ${sqlTime(start)} AND timestamp < ${sqlTime(
    end
  )} AND ${EXCLUSIONS_SQL} ${
    cohort ||
    `AND event IN (${[...QUALIFIED_EVENT_NAMES, "chat_agent_query_completed"]
      .map((e) => `'${e}'`)
      .join(",")})`
  }),
    flagged AS (SELECT *,${FOREGROUND_SQL} fg,${SAVED_CAPTURE_SQL} cap FROM raw),
    qualified AS (SELECT *,${CAPTURE_TIME_SQL} qt FROM flagged)`;
}

/** Six nonoverlapping complete periods, ranking iOS/Android before folding Mobile. */
export function activityQuery(
  end: Date,
  days: number,
  kind: "active" | "saved" | "assistant" = "active",
  periods = 6
) {
  const start = shiftDay(end, -days * periods);
  const predicate =
    kind === "assistant"
      ? "p='macos' AND event='chat_agent_query_completed'"
      : "(fg OR cap)";
  const at = kind === "assistant" ? "timestamp" : "qt";
  return `WITH ${raw(start, end)},
    app_pd AS (SELECT actor,p,intDiv(dateDiff('second',${at},${sqlTime(
    end
  )})-1,${days * 86400}) period,
      uniqExact(toDate(${at})) days,max(${at}) latest,countIf(cap) captures FROM qualified
      WHERE ${predicate} AND ${at} >= ${sqlTime(start)} AND ${at} < ${sqlTime(
    end
  )} GROUP BY actor,p,period),
    ${kind === "active" ? mcpActivityCtes(start, end) + "," : ""}
    pd AS (SELECT * FROM app_pd ${
      kind === "active"
        ? `UNION ALL SELECT actor,'integrations' p,
      intDiv(dateDiff('second',mcp_days.latest,${sqlTime(end)})-1,${
            days * 86400
          }) period,
      count() days,max(mcp_days.latest) latest,0 captures FROM mcp_days GROUP BY actor,period`
        : ""
    }),
    ranked AS (SELECT *,sum(captures) OVER (PARTITION BY actor,period) saved,row_number() OVER (PARTITION BY actor,period ORDER BY (p!='integrations') DESC,days DESC,latest DESC,${PLATFORM_RANK_SQL} ASC) rn FROM pd)
    SELECT period,p,count()${
      kind === "active" ? ",(SELECT count() FROM mcp_raw) marker_rows" : ""
    } FROM ranked WHERE rn=1 ${
    kind === "saved" ? "AND saved>0" : ""
  } GROUP BY period,p
    ${
      kind === "active"
        ? `UNION ALL SELECT -1,'${MCP_MARKER_STATUS_ROW}',0,(SELECT count() FROM mcp_raw)`
        : ""
    }
    LIMIT 100`;
}

/** Entry platform is frozen before outcome filtering, retaining zero-qualified-day people. */
export function cohortQuery(end: Date, maturity: 0 | 2 | 7 | 37, periods = 6) {
  const cohortEnd = shiftDay(end, -maturity);
  const start = shiftDay(cohortEnd, -7 * periods);
  return `WITH ${raw(
    shiftDay(start, -180),
    end,
    `AND person.created_at >= ${sqlTime(
      start
    )} AND person.created_at < ${sqlTime(cohortEnd)}`
  )},
    people AS (SELECT actor,min(anchor) a,
      coalesce(nullIf(argMinIf(p,tuple(timestamp,${PLATFORM_RANK_SQL}),p!='unknown'),''),'unknown') entry,
      min(timestamp) first_event,
      uniqExactIf(toDate(qt),(fg OR cap) AND qt >= anchor AND qt < anchor + interval 7 day) days7,
      countIf((fg OR cap) AND qt >= anchor + interval 1 day AND qt < anchor + interval 2 day) d1,
      countIf((fg OR cap) AND qt >= anchor + interval 7 day AND qt < anchor + interval 37 day) returned,
      countIf(cap AND qt >= anchor AND qt < anchor + interval 7 day) capture
      FROM qualified GROUP BY actor)
    SELECT intDiv(dateDiff('second',a,${sqlTime(
      cohortEnd
    )})-1,604800) period,entry,
      count() denominator,countIf(days7>=2) activated,countIf(days7>=2 AND returned>0) retained,
      countIf(days7<2) nonactivated,countIf(days7<2 AND returned>0) recovered,
      countIf(d1>0) day1,countIf(capture>0) captured
    FROM people WHERE first_event >= a GROUP BY period,entry LIMIT 100`;
}

export function establishedQuery(end: Date, periods = 6) {
  return `WITH ${raw(shiftDay(end, -7 * (periods + 2)), end)},
    weeks AS (SELECT actor,p,intDiv(dateDiff('second',qt,${sqlTime(
      end
    )})-1,604800) w,
      uniqExact(toDate(qt)) days,max(qt) latest FROM qualified WHERE (fg OR cap)
      AND qt >= ${sqlTime(
        shiftDay(end, -7 * (periods + 2))
      )} AND qt < ${sqlTime(end)} GROUP BY actor,p,w),
    windows AS (SELECT arrayJoin([${Array.from(
      { length: periods },
      (_, i) => i
    ).join(",")}]) period),
    denominator_platform AS (SELECT actor,p,period,
      sumIf(days,w IN (period+1,period+2)) prior_days,
      maxIf(latest,w IN (period+1,period+2)) latest,
      countIf(w=period+1)>0 w1,countIf(w=period+2)>0 w2,countIf(w=period)>0 returned
      FROM weeks CROSS JOIN windows GROUP BY actor,p,period),
    people AS (SELECT actor,period,argMax(p,tuple(prior_days,latest,-(${PLATFORM_RANK_SQL}))) p,
      max(w1)>0 AND max(w2)>0 eligible,max(returned)>0 returned
      FROM denominator_platform GROUP BY actor,period)
    SELECT period,p,countIf(eligible),countIf(eligible AND returned) FROM people GROUP BY period,p LIMIT 100`;
}

/** Explicit blocking reads, bounded transient retries, and safe failure categories. */
export const queryPosthog: Query = async (query) => {
  const key = process.env.POSTHOG_PERSONAL_API_KEY;
  const project = process.env.POSTHOG_PROJECT_ID;
  if (!key || !project)
    throw new WallSourceError("PostHog credentials unavailable");
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(
        `${
          process.env.POSTHOG_HOST || "https://us.posthog.com"
        }/api/projects/${project}/query/`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${key}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query: { kind: "HogQLQuery", query: withRowLimit(query) },
            refresh: "blocking",
          }),
          signal: AbortSignal.timeout(120_000),
        }
      );
      if (!res.ok) {
        // Never expose/log the response body, SQL, headers or credential values.
        const reason =
          res.status === 429
            ? "rate limited"
            : res.status === 504
            ? "execution time limit exceeded"
            : [401, 403].includes(res.status)
            ? "access denied"
            : res.status === 400
            ? "query rejected"
            : "service request failed";
        throw new WallSourceError(
          `PostHog ${reason} (HTTP ${res.status})`,
          [429, 502, 503, 504].includes(res.status)
        );
      }
      const data = await res.json();
      if (!Array.isArray(data.results))
        throw new WallSourceError(
          data.query_status
            ? "PostHog query still running"
            : "PostHog aggregate response missing",
          true
        );
      if (data.hasMore || data.results.length >= 100)
        throw new WallSourceError("PostHog aggregate row limit exceeded");
      return Object.assign(data.results, {
        sourceRefreshedAt:
          typeof data.last_refresh === "string" &&
          Number.isFinite(Date.parse(data.last_refresh))
            ? data.last_refresh
            : data.is_cached === true
            ? null
            : new Date().toISOString(),
      });
    } catch (error) {
      const safe =
        error instanceof WallSourceError
          ? error
          : new WallSourceError(
              error instanceof Error &&
              ["TimeoutError", "AbortError"].includes(error.name)
                ? "PostHog request timed out"
                : "PostHog network request failed",
              true
            );
      if (!safe.retryable || attempt >= 2) throw safe;
      await new Promise((resolve) => setTimeout(resolve, 1000 * 2 ** attempt));
    }
  }
};

/** Keep the full trend, but bound each cohort scan/cross-join to two periods.
 * A slow pair is split into individual periods without dropping denominators.
 */
export async function periodQueries(
  query: Query,
  build: (end: Date, periods: number) => string,
  end: Date,
  days: number,
  periods = 6,
  chunkSize = 2
): Promise<AggregateRows> {
  const chunks: AggregateRows[] = [];
  async function read(offset: number, count: number): Promise<void> {
    try {
      const rows = await query(build(shiftDay(end, -days * offset), count));
      chunks.push(
        Object.assign(
          rows.map((r) => [Number(r[0]) + offset, ...r.slice(1)]),
          { sourceRefreshedAt: rows.sourceRefreshedAt ?? null }
        )
      );
    } catch (error) {
      if (
        count === 1 ||
        !(error instanceof WallSourceError) ||
        !error.retryable
      )
        throw error;
      await read(offset, 1);
      await read(offset + 1, 1);
    }
  }
  for (let offset = 0; offset < periods; offset += chunkSize)
    await read(offset, Math.min(chunkSize, periods - offset));
  return Object.assign(chunks.flat(), {
    sourceRefreshedAt: chunks.every((r) => r.sourceRefreshedAt)
      ? chunks.map((r) => r.sourceRefreshedAt!).sort()[0]
      : null,
  });
}
