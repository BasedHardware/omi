/** BigQuery equivalents of the wall's aggregate HogQL row shapes. */
import { isoDay, shiftDay } from "./qualified-activity";
import { DATASET } from "./wall-rollup-extract";
export type RollupRequest =
  | { kind: "growth"; end: Date; periods: number }
  | { kind: "mau"; end: Date; offsets: number[] }
  | { kind: "cohort"; end: Date; maturity: number; periods: number }
  | { kind: "capture"; end: Date }
  | { kind: "established"; end: Date; periods: number }
  | {
      kind: "curve";
      end: Date;
      periods: number;
      observedEnd: Date;
      weeks?: number;
    }
  | { kind: "activity"; end: Date; days: number; periods: number };
const t = (d: Date) => `TIMESTAMP('${isoDay(d)}')`;
const rank = `CASE p WHEN 'macos' THEN 1 WHEN 'ios' THEN 2 WHEN 'android' THEN 3 WHEN 'windows' THEN 4 WHEN 'web' THEN 5 WHEN 'integrations' THEN 6 ELSE 7 END`;
const rows = (fields: string, from: string) =>
  `SELECT TO_JSON_STRING(JSON_ARRAY(${fields})) row ${from}`;
const period = (at: string, end: Date, days = 7) =>
  `DIV(TIMESTAMP_DIFF(${t(end)},${at},MICROSECOND)-1,${
    days * 86400 * 1_000_000
  })`;

export function rollupSql(r: RollupRequest) {
  let start: Date,
    stop = r.end,
    body: string;
  if (r.kind === "mau") {
    start = shiftDay(r.end, -30 - Math.max(...r.offsets));
    body = rows(
      "off,COUNT(DISTINCT actor)",
      `FROM UNNEST([${r.offsets.join(
        ","
      )}]) off LEFT JOIN active a ON a.latest >= TIMESTAMP_SUB(${t(
        r.end
      )},INTERVAL (30+off) DAY) AND a.latest < TIMESTAMP_SUB(${t(
        r.end
      )},INTERVAL off DAY) AND a.day >= DATE_SUB(DATE(${t(
        r.end
      )}),INTERVAL (30+off) DAY) AND a.day < DATE_SUB(DATE(${t(
        r.end
      )}),INTERVAL off DAY) WHERE EXISTS(SELECT 1 FROM active) GROUP BY off`
    );
  } else if (r.kind === "growth" || r.kind === "activity") {
    const days = r.kind === "growth" ? 7 : r.days;
    start = shiftDay(
      r.end,
      -days * (r.periods + (r.kind === "growth" ? 1 : 0))
    );
    const ranked = `pd AS (SELECT actor,p,${period(
      "latest",
      r.end,
      days
    )} period,COUNT(DISTINCT activity_day) days,MAX(latest) latest FROM active GROUP BY actor,p,period),
      ap AS (SELECT actor,period,ARRAY_AGG(p ORDER BY (p!='integrations') DESC,days DESC,latest DESC,${rank} LIMIT 1)[OFFSET(0)] p FROM pd GROUP BY actor,period),
      ad AS (SELECT actor,${period(
        "latest",
        r.end,
        days
      )} period,COUNT(DISTINCT activity_day) n FROM active GROUP BY actor,period)`;
    if (r.kind === "activity")
      body =
        `WITH ${ranked} ` +
        rows("period,p,COUNT(*)", "FROM ap GROUP BY period,p");
    else
      body =
        `WITH ${ranked},
      anchors AS (SELECT actor,MIN(anchor) anchor FROM data WHERE kind='activity' GROUP BY actor),
      labelled AS (SELECT a.*,d.n,prior.actor IS NOT NULL retained,
        prior.actor IS NULL AND i.anchor >= TIMESTAMP_SUB(${t(
          r.end
        )},INTERVAL (7*(a.period+1)) DAY) fresh
        FROM ap a JOIN ad d USING(actor,period) LEFT JOIN ap prior ON a.actor=prior.actor AND prior.period=a.period+1 LEFT JOIN anchors i ON a.actor=i.actor),
      result AS (
        SELECT period,p label,COUNT(*) people,SUM(n) person_days,COUNTIF(retained) retained,COUNTIF(fresh) fresh FROM labelled WHERE period<${
          r.periods
        } GROUP BY period,p
        UNION ALL SELECT prior.period-1,'__churned',COUNT(*),0,0,0 FROM ap prior LEFT JOIN ap cur ON prior.actor=cur.actor AND cur.period=prior.period-1 WHERE prior.period BETWEEN 1 AND ${
          r.periods
        } AND cur.actor IS NULL GROUP BY prior.period
        UNION ALL SELECT period,CONCAT('__days_',CAST(LEAST(n,7) AS STRING)),COUNT(*),0,0,0 FROM ad WHERE period<${
          r.periods
        } GROUP BY period,n
      ) ` +
        rows("period,label,people,person_days,retained,fresh", "FROM result");
  } else if (r.kind === "established") {
    start = shiftDay(r.end, -7 * (r.periods + 2));
    body =
      `WITH weeks AS (SELECT actor,p,${period(
        "latest",
        r.end
      )} w,COUNT(DISTINCT activity_day) days,MAX(latest) latest FROM app_active GROUP BY actor,p,w),
      dp AS (SELECT actor,p,k period,SUM(IF(w IN (k+1,k+2),days,0)) prior_days,MAX(IF(w IN (k+1,k+2),latest,NULL)) latest,
        COUNTIF(w=k+1)>0 w1,COUNTIF(w=k+2)>0 w2,COUNTIF(w=k)>0 returned FROM weeks CROSS JOIN UNNEST(GENERATE_ARRAY(0,${
          r.periods - 1
        })) k GROUP BY actor,p,k),
      people AS (SELECT actor,period,ARRAY_AGG(p ORDER BY prior_days DESC,latest DESC,${rank} LIMIT 1)[OFFSET(0)] p,LOGICAL_OR(w1) AND LOGICAL_OR(w2) eligible,LOGICAL_OR(returned) returned FROM dp GROUP BY actor,period)
      ` +
      rows(
        "period,p,COUNTIF(eligible),COUNTIF(eligible AND returned)",
        "FROM people GROUP BY period,p"
      );
  } else {
    const maturity =
      r.kind === "cohort" ? r.maturity : r.kind === "capture" ? 7 : 0;
    const cohortEnd = shiftDay(r.end, -maturity);
    const periods = r.kind === "capture" ? 1 : r.periods;
    const cohortStart = shiftDay(cohortEnd, -7 * periods);
    start = shiftDay(cohortStart, -180);
    if (r.kind === "curve") stop = r.observedEnd;
    const cohort = `identities AS (SELECT actor,MIN(anchor) a,MIN(first_at) first_event,
        COALESCE(ARRAY_AGG(IF(p!='unknown',STRUCT(first_at,p),NULL) IGNORE NULLS ORDER BY first_at,${rank} LIMIT 1)[SAFE_OFFSET(0)].p,'unknown') entry
      FROM data WHERE kind='identity' AND anchor >= ${t(
        cohortStart
      )} AND anchor < ${t(cohortEnd)} GROUP BY actor),
      people AS (SELECT i.*,${period("a", cohortEnd)} period,
        COUNT(DISTINCT IF(f.kind='activity' AND f.age_day BETWEEN 0 AND 6,f.activity_day,NULL)) days7,
        COUNTIF(f.kind='activity' AND f.age_day=1)>0 d1,
        COUNTIF(f.kind='activity' AND f.age_day BETWEEN 7 AND 36)>0 returned,
        COUNTIF(f.kind='activity' AND f.saved AND f.age_day BETWEEN 0 AND 6)>0 captured
        FROM identities i LEFT JOIN data f ON i.actor=f.actor GROUP BY i.actor,a,first_event,entry HAVING first_event>=a)`;
    if (r.kind === "cohort")
      body =
        `WITH ${cohort} ` +
        rows(
          "period,entry,COUNT(*),COUNTIF(days7>=2),COUNTIF(days7>=2 AND returned),COUNTIF(days7<2),COUNTIF(days7<2 AND returned),COUNTIF(d1),COUNTIF(captured)",
          "FROM people GROUP BY period,entry"
        );
    else if (r.kind === "curve")
      body =
        `WITH ${cohort},
      eligible AS (SELECT cp.*,k,TIMESTAMP_ADD(a,INTERVAL (7*(k+1)) DAY) <= ${t(
        stop
      )} observed,
        EXISTS(SELECT 1 FROM data f WHERE f.actor=cp.actor AND f.kind='activity' AND f.age_day>=7*k AND f.age_day<7*(k+1)) active FROM people cp CROSS JOIN UNNEST(GENERATE_ARRAY(0,${
          (r.weeks ?? 9) - 1
        })) k)
      ` +
        rows(
          "period,k,COUNTIF(observed),COUNTIF(observed AND active)",
          "FROM eligible GROUP BY period,k HAVING COUNTIF(observed)>0"
        );
    else
      body =
        `WITH ${cohort},
      evidence AS (SELECT cp.actor,cp.days7,
        ARRAY_AGG(DISTINCT IF(f.family!='',f.family,NULL) IGNORE NULLS) hws,
        COUNTIF(f.phone)>0 phone,COUNTIF(f.mac)>0 mac FROM people cp LEFT JOIN data f ON cp.actor=f.actor AND f.kind='capture' AND f.age_day BETWEEN 0 AND 6 GROUP BY cp.actor,cp.days7),
      clean AS (SELECT *,ARRAY(SELECT h FROM UNNEST(hws) h WHERE h!='Omi unspecified' OR NOT EXISTS(SELECT 1 FROM UNNEST(hws) x WHERE x IN ('Omi pendant','Omi devkit','Omi Glass','Omi Neo'))) hc FROM evidence),
      segments AS (SELECT *,CASE WHEN ARRAY_LENGTH(hc)>1 THEN 'Multiple devices' WHEN ARRAY_LENGTH(hc)=1 AND hc[OFFSET(0)] IN ('Omi pendant','Limitless','Apple Watch') THEN hc[OFFSET(0)] WHEN ARRAY_LENGTH(hc)=1 AND hc[OFFSET(0)]='Omi unspecified' THEN 'Omi, model unknown' WHEN ARRAY_LENGTH(hc)=1 THEN 'Other device' WHEN phone AND mac THEN 'Phone + Mac' WHEN mac THEN 'Mac only' WHEN phone THEN 'Phone mic only' ELSE 'No capture' END segment FROM clean)
      ` +
        rows(
          "segment,COUNT(*),COUNTIF(days7>=2)",
          "FROM segments GROUP BY segment"
        );
  }
  // Activity parity checks include the snapshot's 30-day marker probe.
  // Growth returns no marker-status row; its counts depend only on its activity window.
  if (r.kind === "activity" && +start > +shiftDay(stop, -30))
    start = shiftDay(stop, -30);
  const ctes = `data AS (SELECT * FROM \`${DATASET}.person_day\` WHERE day >= @start AND day < @stop AND definition=@definition AND key_id=@keyId),
    app_active AS (SELECT * FROM data WHERE kind='activity' AND day >= DATE(@activityStart) AND latest >= @activityStart AND latest < TIMESTAMP(@stop)),
    active AS (SELECT * FROM data WHERE kind IN ('activity','mcp') AND day >= DATE(@activityStart) AND latest >= @activityStart AND latest < TIMESTAMP(@stop))`;
  // Activity window is distinct from the extended MCP marker observation range.
  const activityStart =
    r.kind === "growth"
      ? shiftDay(r.end, -7 * (r.periods + 1))
      : r.kind === "activity"
      ? shiftDay(r.end, -r.days * r.periods)
      : start;
  return {
    start,
    stop,
    activityStart,
    query: `WITH ${ctes}, receipts AS (
      SELECT * FROM \`${DATASET}.coverage\` WHERE day>=@start AND day<@stop AND definition=@definition AND key_id=@keyId
    ) SELECT (SELECT COUNT(DISTINCT day) FROM receipts) covered,
      (SELECT CAST(MIN(refreshed_at) AS STRING) FROM receipts) refreshed,
      ARRAY(SELECT row FROM (${body})) AS \`rows\``,
  };
}
