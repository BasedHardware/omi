/** Read-only BigQuery SQL acceptance over synthetic literals, no datasets needed. */
import {
  BigQuery,
  BigQueryDate,
  BigQueryTimestamp,
} from "@google-cloud/bigquery";
import { expect, it } from "vitest";
import { rollupSql, RollupRequest } from "../wall-rollup-sql";
import { DATASET } from "../wall-rollup-extract";
import { isoDay } from "../qualified-activity";
const end = new Date("2026-10-13T00:00:00Z");
const anchors: Record<string, string> = {
  a: "2026-09-29T12:00:00Z",
  b: "2026-09-30T12:00:00Z",
  c: "2026-10-10T12:00:00Z",
  d: "2026-09-01T12:00:00Z",
  e: "2026-09-01T12:00:00Z",
  m: "1970-01-01T00:00:00Z",
};
function row(
  actor: string,
  day: string,
  p: string,
  kind = "activity",
  extra = {}
) {
  const at = day + "T13:00:00Z";
  return {
    day,
    actor,
    p,
    kind,
    anchor: anchors[actor],
    first_at: kind === "identity" ? anchors[actor] : at,
    latest: at,
    activity_day: day,
    age_day: Math.floor(
      (Date.parse(at) - Date.parse(anchors[actor])) / 86400000
    ),
    saved: false,
    family: "",
    phone: false,
    mac: false,
    n: 1,
    ...extra,
  };
}
const features = [
  row("a", "2026-09-29", "macos", "identity"),
  row("b", "2026-09-30", "web", "identity"),
  row("c", "2026-10-10", "macos", "identity"),
  row("d", "2026-09-01", "ios", "identity"),
  row("e", "2026-09-01", "macos", "identity"),
  row("a", "2026-09-29", "macos", "activity", { saved: true }),
  row("a", "2026-09-30", "ios"),
  row("a", "2026-10-06", "ios"),
  row("a", "2026-10-07", "ios"),
  row("a", "2026-10-12", "macos"),
  row("a", "2026-09-29", "macos", "capture", { family: "Omi pendant" }),
  row("c", "2026-10-12", "macos"),
  row("d", "2026-10-01", "ios"),
  row("e", "2026-09-23", "macos"),
  row("e", "2026-09-30", "ios"),
  row("e", "2026-10-07", "macos"),
  row("m", "2026-10-12", "integrations", "mcp"),
  row("a", "2026-10-12", "integrations", "mcp"),
];

let fixtureClient: BigQuery | undefined;
async function run(request: RollupRequest, population = features) {
  const bq = (fixtureClient ||= new BigQuery({ projectId: "based-hardware" }));
  const spec = rollupSql(request);
  const typed = ["day", "activity_day"]
    .map((k) => `DATE(JSON_VALUE(j,'$.${k}')) ${k}`)
    .concat(
      ["anchor", "first_at", "latest"].map(
        (k) => `TIMESTAMP(JSON_VALUE(j,'$.${k}')) ${k}`
      )
    )
    .concat(
      ["actor", "p", "kind", "family"].map((k) => `JSON_VALUE(j,'$.${k}') ${k}`)
    )
    .concat(
      ["age_day", "n"].map((k) => `CAST(JSON_VALUE(j,'$.${k}') AS INT64) ${k}`)
    )
    .concat(
      ["saved", "phone", "mac"].map(
        (k) => `CAST(JSON_VALUE(j,'$.${k}') AS BOOL) ${k}`
      )
    )
    .join(",");
  let sql = spec.query.replace(
    /SELECT \* FROM `based-hardware\.omi_tv\.person_day` WHERE [^)]*?key_id=@keyId/,
    `SELECT ${typed} FROM UNNEST(JSON_QUERY_ARRAY(@features)) j WHERE DATE(JSON_VALUE(j,'$.day'))>=@start AND DATE(JSON_VALUE(j,'$.day'))<@stop`
  );
  sql = sql.replace(
    /SELECT \* FROM `based-hardware\.omi_tv\.coverage` WHERE [^)]*?key_id=@keyId/,
    "SELECT day,TIMESTAMP('2026-10-13') refreshed_at FROM UNNEST(GENERATE_DATE_ARRAY(@start,DATE_SUB(@stop,INTERVAL 1 DAY))) day"
  );
  expect(sql).not.toContain(DATASET);
  console.info("synthetic SQL:", request.kind);
  const [out] = await bq.query({
    query: sql,
    params: {
      start: new BigQueryDate(isoDay(spec.start)),
      stop: new BigQueryDate(isoDay(spec.stop)),
      activityStart: new BigQueryTimestamp(spec.activityStart),
      features: JSON.stringify(population),
    },
    location: "US",
    maximumBytesBilled: "10485760",
    jobTimeoutMs: 30_000,
  });
  expect(new Date(out[0].refreshed).toISOString()).toBe(
    "2026-10-13T00:00:00.000Z"
  );
  return (out[0].rows as string[]).map(
    (x) => JSON.parse(x) as (string | number)[]
  );
}

it.skipIf(process.env.OMI_TV_ROLLUP_SQL_CHECK !== "1")(
  "executes every aggregate SQL against a population with known counts and clock boundaries",
  async () => {
    const growth = await run({ kind: "growth", end, periods: 1 });
    expect(growth).toContainEqual([0, "ios", 1, 3, 1, 0]);
    expect(growth).toContainEqual([0, "macos", 2, 2, 1, 1]);
    expect(growth).toContainEqual([0, "integrations", 1, 1, 0, 0]);
    expect(growth).toContainEqual([0, "__churned", 1, 0, 0, 0]);
    expect(growth).toContainEqual([0, "__days_1", 3, 0, 0, 0]);
    expect(growth).toContainEqual([0, "__days_3", 1, 0, 0, 0]);
    const mau = await run({ kind: "mau", end, offsets: [0, 1] });
    expect(mau).toContainEqual([0, 5]);
    expect(mau).toContainEqual([1, 3]);
    const activity = await run({ kind: "activity", end, days: 7, periods: 1 });
    expect(activity).toContainEqual([0, "ios", 1]);
    expect(activity).toContainEqual([0, "macos", 2]);
    expect(activity).toContainEqual([0, "integrations", 1]);
    const cohort = await run({ kind: "cohort", end, maturity: 7, periods: 1 });
    expect(cohort).toContainEqual([0, "macos", 1, 1, 1, 0, 0, 1, 1]);
    expect(cohort).toContainEqual([0, "web", 1, 0, 0, 1, 0, 0, 0]);
    const capture = await run({ kind: "capture", end });
    expect(capture).toContainEqual(["Omi pendant", 1, 1]);
    expect(capture).toContainEqual(["No capture", 1, 0]);
    const established = await run({ kind: "established", end, periods: 1 });
    expect(established).toContainEqual([0, "ios", 1, 1]);
    const curve = await run({
      kind: "curve",
      end: new Date("2026-10-06T00:00:00Z"),
      periods: 1,
      observedEnd: end,
    });
    expect(curve).toContainEqual([0, 0, 2, 1]);
    expect(await run({ kind: "mau", end, offsets: [0, 1] }, [])).toEqual([]); // no telemetry stays absent
    expect(curve.some((r) => r[1] === 1)).toBe(false); // not all cohort members have a completed W1
  },
  300_000
);

it.skipIf(process.env.OMI_TV_ROLLUP_SQL_CHECK !== "1")(
  "UTC boundary is exact to the microsecond",
  async () => {
    const atBoundary = await run(
      { kind: "activity", end, days: 7, periods: 2 },
      [
        row("a", "2026-10-05", "ios", "activity", {
          first_at: "2026-10-05T23:59:59.999999Z",
          latest: "2026-10-05T23:59:59.999999Z",
        }),
        row("d", "2026-10-06", "macos", "activity", {
          first_at: "2026-10-06T00:00:00.000000Z",
          latest: "2026-10-06T00:00:00.000000Z",
          age_day: 34,
        }),
      ]
    );
    expect(atBoundary).toContainEqual([1, "ios", 1]);
    expect(atBoundary).toContainEqual([0, "macos", 1]);
  },
  300_000
);
