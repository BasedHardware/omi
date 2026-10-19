/** Keyless Cloud Run Job. One day per extraction, atomic day + receipt replace. */
import {
  BigQuery,
  BigQueryDate,
  BigQueryTimestamp,
} from "@google-cloud/bigquery";
import { Readable } from "stream";
import { randomUUID } from "crypto";
import {
  closedDay,
  DATASET,
  extractDay,
  keyId,
  ROLLUP_VERSION,
} from "../../lib/wall-rollup-extract";
import { isoDay, shiftDay, utcDay } from "../../lib/qualified-activity";

export async function queryPage(query: string) {
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";
  const project = process.env.POSTHOG_PROJECT_ID;
  const key = process.env.POSTHOG_PERSONAL_API_KEY;
  if (!key || !project) throw new Error("PostHog configuration unavailable");
  for (let attempt = 0; attempt < 3; attempt++) {
    let response: Response;
    try {
      response = await fetch(`${host}/api/projects/${project}/query/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: { kind: "HogQLQuery", query },
          refresh: "blocking",
        }),
        signal: AbortSignal.timeout(120_000),
      });
    } catch {
      if (attempt === 2) throw new Error("PostHog request timed out or failed");
      await new Promise((resolve) => setTimeout(resolve, 2000 * 2 ** attempt));
      continue;
    }
    if ([429, 502, 503, 504].includes(response.status) && attempt < 2) {
      await new Promise((resolve) => setTimeout(resolve, 2000 * 2 ** attempt));
      continue;
    }
    if (!response.ok) throw new Error(`PostHog HTTP ${response.status}`);
    const data = await response.json();
    if (
      !Array.isArray(data.results) ||
      (data.hasMore === true && data.results.length < 5000) ||
      data.is_cached === true ||
      data.query_status?.complete === false
    )
      throw new Error("PostHog fresh complete page unavailable");
    return {
      results: data.results,
      sourceRefreshedAt:
        typeof data.last_refresh === "string"
          ? data.last_refresh
          : new Date().toISOString(),
    };
  }
  throw new Error("PostHog retry budget exceeded");
}

export async function writeDay(
  bq: BigQuery,
  day: string,
  extract = extractDay
) {
  closedDay(day);
  const key = process.env.CRON_SECRET || "";
  keyId(key); // validate before any source request
  const data = await extract(day, key, queryPage);
  // Only HMAC values and closed-enum features reach the load stream. No raw IDs
  // in temp files, SQL parameters, BigQuery job logs or Cloud Logging.
  const stage = `stage_${randomUUID().replace(/-/g, "")}`;
  const table = bq.dataset("omi_tv").table(stage);
  try {
    const [schema] = await bq
      .dataset("omi_tv")
      .table("person_day")
      .getMetadata();
    await table.create({
      schema: schema.schema,
      expirationTime: Date.now() + 3_600_000,
    });
    await new Promise<void>((resolve, reject) => {
      const stream = table.createWriteStream({
        sourceFormat: "NEWLINE_DELIMITED_JSON",
        writeDisposition: "WRITE_TRUNCATE",
      });
      stream.on("complete", () => resolve());
      stream.on("error", reject);
      Readable.from(data.rows.map((r) => JSON.stringify(r) + "\n")).pipe(
        stream
      );
    });
    // Concurrent attempts either serialize/commit or abort. A partial page/load
    // cannot erase a previously published day. Receipt is in the same transaction.
    await bq.query({
      query: `BEGIN TRANSACTION;
      DELETE FROM \`${DATASET}.person_day\` WHERE day=@day;
      INSERT INTO \`${DATASET}.person_day\` SELECT * FROM \`${DATASET}.${stage}\`;
      DELETE FROM \`${DATASET}.coverage\` WHERE day=@day;
      INSERT INTO \`${DATASET}.coverage\` (day,definition,key_id,refreshed_at,loaded_at,feature_rows,pages)
        VALUES(@day,@definition,@keyId,@refreshed,CURRENT_TIMESTAMP(),@rows,@pages);
      COMMIT TRANSACTION;`,
      location: "US",
      maximumBytesBilled: String(1024 * 1024 * 1024),
      jobTimeoutMs: 120_000,
      params: {
        day: new BigQueryDate(day),
        definition: ROLLUP_VERSION,
        keyId: keyId(key),
        refreshed: new BigQueryTimestamp(data.refreshedAt!),
        rows: data.rows.length,
        pages: data.pages,
      },
    });
    console.info(
      JSON.stringify({
        event: "wall_rollup_day",
        day,
        rows: data.rows.length,
        pages: data.pages,
        outcome: "published",
      })
    );
  } finally {
    await table.delete({ ignoreNotFound: true }).catch(() => {});
  }
}

export function datesForRun(
  today: Date,
  present: Set<string>,
  explicit?: string
): string[] {
  if (explicit) {
    closedDay(explicit, today);
    return [explicit];
  }
  const frontier = isoDay(shiftDay(utcDay(today), -1));
  const missing = Array.from({ length: 13 }, (_, i) =>
    isoDay(shiftDay(utcDay(today), i - 14))
  )
    .filter((d) => !present.has(d))
    .slice(0, 2);
  // Re-extract yesterday plus the previous two arrival days for late ingestion /
  // person merges, and at most two missing days (one day per call, serial).
  return Array.from(
    new Set([
      frontier,
      isoDay(shiftDay(utcDay(today), -2)),
      isoDay(shiftDay(utcDay(today), -3)),
      ...missing,
    ])
  );
}
export async function main() {
  const bq = new BigQuery({ projectId: "based-hardware" }); // attached SA / ADC only
  const explicit = process.env.OMI_TV_ROLLUP_DATE;
  const present = new Set<string>();
  if (!explicit) {
    const [rows] = await bq.query({
      query: `SELECT FORMAT_DATE('%F',day) day FROM \`${DATASET}.coverage\` WHERE day>=DATE_SUB(CURRENT_DATE('UTC'),INTERVAL 14 DAY) AND day<CURRENT_DATE('UTC') AND definition=@definition AND key_id=@keyId`,
      params: {
        definition: ROLLUP_VERSION,
        keyId: keyId(process.env.CRON_SECRET || ""),
      },
      location: "US",
      maximumBytesBilled: String(10 * 1024 * 1024),
    });
    for (const row of rows) present.add(row.day);
  }
  for (const day of datesForRun(new Date(), present, explicit)) {
    await writeDay(bq, day);
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
}
