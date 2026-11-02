import { captureEvidenceCtes } from "./wall-capture-sql";
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

/** Qualified actor × platform × period rows and the primary-platform ranking.
 * Shared by the snapshot activity query and the v3 weekly growth series, so both
 * count exactly the same people for a period.
 */
function activityCtes(
  start: Date,
  end: Date,
  days: number,
  kind: "active" | "saved" | "assistant",
  extra = { app: "", mcp: "" }
) {
  const predicate =
    kind === "assistant"
      ? "p='macos' AND event='chat_agent_query_completed'"
      : "(fg OR cap)";
  const at = kind === "assistant" ? "timestamp" : "qt";
  return `${raw(start, end)},
    app_pd AS (SELECT actor,p,intDiv(dateDiff('second',${at},${sqlTime(
    end
  )})-1,${days * 86400}) period,
      uniqExact(${UTC_DAY(at)}) days,max(${at}) latest,countIf(cap) captures${
    extra.app
  } FROM qualified
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
      count() days,max(mcp_days.latest) latest,0 captures${
        extra.mcp
      } FROM mcp_days GROUP BY actor,period`
        : ""
    }),
    ranked AS (SELECT *,sum(captures) OVER (PARTITION BY actor,period) saved,row_number() OVER (PARTITION BY actor,period ORDER BY (p!='integrations') DESC,days DESC,latest DESC,${PLATFORM_RANK_SQL} ASC) rn FROM pd)`;
}

/** Six nonoverlapping complete periods, ranking iOS/Android before folding Mobile. */
export function activityQuery(
  end: Date,
  days: number,
  kind: "active" | "saved" | "assistant" = "active",
  periods = 6
) {
  const start = shiftDay(end, -days * periods);
  return `WITH ${activityCtes(start, end, days, kind)}
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

export const CHURNED_ROW = "__churned";
export const DAYS_ROW_PREFIX = "__days_";
/** UTC day number: HogQL's toDate() follows the project timezone. */
const UTC_DAY = (at: string) => `intDiv(toUnixTimestamp(${at}),86400)`;

/** v3 weekly growth: the snapshot's qualified actors and primary platform per
 * trailing 7-day period, plus growth accounting, person-days and the L1–L7
 * histogram. Scans one extra period so the oldest returned period still knows
 * who was active the week before. One pass per actor (CTEs are inlined, so no
 * joins): the primary platform is the snapshot ranking's first row via argMax.
 * Columns: period, label, people, person_days, retained, new. `label` is the
 * primary platform, CHURNED_ROW (prior-period people absent this period) or
 * DAYS_ROW_PREFIX + qualified UTC days in the period; those reuse `people`.
 */
export function weeklyGrowthQuery(end: Date, periods = 4) {
  const start = shiftDay(end, -7 * (periods + 1));
  const stop = sqlTime(end);
  const el = (t: string, i: number) => `tupleElement(${t},${i})`;
  return `WITH ${activityCtes(start, end, 7, "active", {
    app: `,groupUniqArray(${UTC_DAY("qt")}) ds,min(anchor) a`,
    mcp: `,groupUniqArray(mcp_days.utc_day) ds,toDateTime('1970-01-01 00:00:00','UTC') a`,
  })},
    ap AS (SELECT actor,period,
        argMax(p,tuple(p!='integrations',days,latest,-(${PLATFORM_RANK_SQL}))) primary,
        length(groupUniqArrayArray(ds)) n,
        minIf(a,p!='integrations') anchor
      FROM pd GROUP BY actor,period),
    pa AS (SELECT actor,groupArray(tuple(period,primary,n)) rs,groupArray(period) ps,
        minIf(anchor,anchor > toDateTime('1970-01-01 00:00:00','UTC')) first_seen
      FROM ap GROUP BY actor),
    labelled AS (SELECT arrayConcat(
        arrayMap(r -> tuple(${el("r", 2)},${el("r", 1)},${el(
    "r",
    3
  )},has(ps,${el("r", 1)}+1),
          NOT has(ps,${el(
            "r",
            1
          )}+1) AND first_seen > toDateTime('1970-01-01 00:00:00','UTC')
          AND first_seen >= ${stop} - toIntervalDay(7*(${el("r", 1)}+1))),rs),
        arrayMap(q -> tuple('${CHURNED_ROW}',q-1,0,false,false),arrayFilter(q -> q >= 1 AND NOT has(ps,q-1),ps)),
        arrayMap(r -> tuple(concat('${DAYS_ROW_PREFIX}',toString(least(${el(
    "r",
    3
  )},7))),${el("r", 1)},0,false,false),rs)) ts FROM pa)
    SELECT ${el("t", 2)} period,${el("t", 1)} label,count(),sum(${el(
    "t",
    3
  )}),countIf(${el("t", 4)}),countIf(${el("t", 5)})
    FROM labelled ARRAY JOIN ts AS t WHERE ${el("t", 2)} < ${periods}
    GROUP BY period,label LIMIT 100`;
}

/** Qualified MAU (snapshot definition, MCP included) for 30-day windows ending
 * `offset` complete days before `end`. One row per offset: offset, people.
 * Like the snapshot, an event counts only when both its qualified time and its
 * ingestion timestamp fall inside the window (client clocks can disagree).
 */
export function mauOffsetsQuery(end: Date, offsets: number[]) {
  const start = shiftDay(end, -(Math.max(...offsets) + 30));
  const stop = sqlTime(end);
  const ago = (at: string) =>
    `intDiv(dateDiff('second',${at},${stop})-1,86400)`;
  return `WITH ${raw(start, end)},${mcpActivityCtes(start, end)},
    ad AS (SELECT actor,groupUniqArray(tuple(lo,hi)) spans FROM (
        SELECT actor,least(${ago("qt")},${ago("timestamp")}) lo,greatest(${ago(
    "qt"
  )},${ago("timestamp")}) hi
        FROM qualified WHERE (fg OR cap) AND qt >= ${sqlTime(
          start
        )} AND qt < ${stop}
        UNION ALL SELECT actor,${ago("latest")} lo,${ago(
    "latest"
  )} hi FROM mcp_days)
      GROUP BY actor)
    SELECT o,countIf(arrayExists(s -> tupleElement(s,1) >= o AND tupleElement(s,2) < o + 30,spans)) FROM ad
    ARRAY JOIN [${offsets.join(",")}] AS o GROUP BY o LIMIT 100`;
}

/** Weekly first-seen cohorts (snapshot cohort anchor and 180-day history check),
 * qualified in week k after the anchor. A person contributes to week k only
 * once that week is fully observed before `observedEnd`.
 * Columns: period, week, observed people, active people.
 */
export function retentionCurveQuery(
  end: Date,
  periods: number,
  observedEnd: Date,
  weeks = 9
) {
  const start = shiftDay(end, -7 * periods);
  const obs = sqlTime(observedEnd);
  return `WITH ${raw(
    shiftDay(start, -180),
    observedEnd,
    `AND person.created_at >= ${sqlTime(
      start
    )} AND person.created_at < ${sqlTime(end)}`
  )},
    people AS (SELECT actor,min(anchor) a,min(timestamp) first_event,
      groupUniqArrayIf(intDiv(dateDiff('second',anchor,qt),604800),(fg OR cap) AND qt >= anchor) active_weeks
      FROM qualified GROUP BY actor)
    SELECT intDiv(dateDiff('second',a,${sqlTime(end)})-1,604800) period,k,
      countIf(a + toIntervalDay(7*(k+1)) <= ${obs}) observed,
      countIf(a + toIntervalDay(7*(k+1)) <= ${obs} AND has(active_weeks,k)) active
    FROM people ARRAY JOIN range(${weeks}) AS k
    WHERE first_event >= a GROUP BY period,k HAVING observed > 0 LIMIT 100`;
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
      uniqExactIf(${UTC_DAY(
        "qt"
      )},(fg OR cap) AND qt >= anchor AND qt < anchor + interval 7 day) days7,
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
      uniqExact(${UTC_DAY(
        "qt"
      )}) days,max(qt) latest FROM qualified WHERE (fg OR cap)
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

/** PostHog's blocking budget (~10 s since 2026-10-16) is far below what the
 * wall's multi-week scans need, while async queries run to completion. */
export const ASYNC_POLL_MS = 2_000;
export const ASYNC_DEADLINE_MS = 240_000;

function httpFailure(status: number) {
  // Never expose/log the response body, SQL, headers or credential values.
  const reason =
    status === 429
      ? "rate limited"
      : status === 504
      ? "execution time limit exceeded"
      : [401, 403].includes(status)
      ? "access denied"
      : status === 400
      ? "query rejected"
      : "service request failed";
  return new WallSourceError(
    `PostHog ${reason} (HTTP ${status})`,
    [429, 502, 503, 504].includes(status)
  );
}

type QueryStatus = {
  id?: unknown;
  complete?: unknown;
  error?: unknown;
  error_message?: unknown;
  results?: unknown;
};

/** Poll an async HogQL query until it completes, fails or the deadline passes. */
async function awaitAsync(
  url: string,
  key: string,
  initial: QueryStatus
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + ASYNC_DEADLINE_MS;
  let status = initial;
  for (;;) {
    if (status.complete === true) {
      if (status.error)
        throw new WallSourceError(
          /execution time/i.test(String(status.error_message ?? ""))
            ? "PostHog execution time limit exceeded (async)"
            : "PostHog async query failed",
          true
        );
      if (status.results && typeof status.results === "object")
        return status.results as Record<string, unknown>;
      throw new WallSourceError("PostHog aggregate response missing", true);
    }
    if (typeof status.id !== "string" || Date.now() >= deadline)
      throw new WallSourceError("PostHog request timed out", true);
    await new Promise((resolve) => setTimeout(resolve, ASYNC_POLL_MS));
    const res = await fetch(`${url}${encodeURIComponent(status.id)}/`, {
      headers: { Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw httpFailure(res.status);
    const body = await res.json();
    status = (body?.query_status ?? body) as QueryStatus;
  }
}

/** Async reads polled to completion (cached results return at once), bounded
 * transient retries, and safe failure categories. */
export const queryPosthog: Query = async (query) => {
  const key = process.env.POSTHOG_PERSONAL_API_KEY;
  const project = process.env.POSTHOG_PROJECT_ID;
  if (!key || !project)
    throw new WallSourceError("PostHog credentials unavailable");
  const url = `${
    process.env.POSTHOG_HOST || "https://us.posthog.com"
  }/api/projects/${project}/query/`;
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: { kind: "HogQLQuery", query: withRowLimit(query) },
          refresh: "async",
        }),
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) throw httpFailure(res.status);
      let data = await res.json();
      if (!Array.isArray(data.results) && data.query_status)
        data = await awaitAsync(url, key, data.query_status);
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

export const CAPTURE_SEGMENTS = [
  "Omi pendant",
  "Multiple devices",
  "Limitless",
  "Apple Watch",
  "Other device",
  "Omi, model unknown",
  "Phone + Mac",
  "Mac only",
  "Phone mic only",
  "No capture",
] as const;

/** Week-one activation by first-week capture source for the latest matured
 * weekly cohort: the snapshot cohort (same anchor, 180-day history check and
 * ≥2 qualified days), so segment people sum to the activation denominator.
 * Exclusive segments follow the 2026-10-15 device-surface audit: any hardware
 * family evidence first (more than one family = multiple devices), then
 * phone mic / Mac capture, else no capture. Columns: segment, people, activated.
 */
export function captureSourceQuery(end: Date) {
  const cohortEnd = shiftDay(end, -7);
  const start = shiftDay(cohortEnd, -7);
  const week = (at: string) =>
    `${at} >= anchor AND ${at} < anchor + interval 7 day`;
  return `WITH ${raw(
    shiftDay(start, -180),
    end,
    `AND person.created_at >= ${sqlTime(
      start
    )} AND person.created_at < ${sqlTime(cohortEnd)}`
  )},
    ${captureEvidenceCtes()},
    people AS (SELECT actor,min(anchor) a,min(timestamp) first_event,
      uniqExactIf(${UTC_DAY("qt")},(fg OR cap) AND ${week("qt")}) days7,
      groupUniqArrayIf(h,h!='' AND ${week("et")}) hws,
      countIf(phone AND ${week("et")}) > 0 ph,countIf(mac AND ${week(
    "et"
  )}) > 0 mc
      FROM hw GROUP BY actor),
    seg AS (SELECT *,arrayFilter(x -> x!='Omi unspecified' OR NOT hasAny(hws,['Omi pendant','Omi devkit','Omi Glass','Omi Neo']),hws) hc
      FROM people WHERE first_event >= a)
    SELECT multiIf(length(hc)>1,'Multiple devices',length(hc)=1 AND hc[1] IN ('Omi pendant','Limitless','Apple Watch'),hc[1],
      length(hc)=1 AND hc[1]='Omi unspecified','Omi, model unknown',length(hc)=1,'Other device',
      ph AND mc,'Phone + Mac',mc,'Mac only',ph,'Phone mic only','No capture') segment,
      count(),countIf(days7>=2) FROM seg GROUP BY segment LIMIT 100`;
}
