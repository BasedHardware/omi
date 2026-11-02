/** Keyless Cloud Run Job: meters yesterday and today (UTC) from Cloud Monitoring
 * and writes the live document `admin_stats_payload_cache/wall-live:v1`.
 * Read-only against Monitoring; the only write is that one document, in a
 * transaction. Query set ported from the marginmeter prototype (margin.py).
 * Needs roles/monitoring.viewer on based-hardware and datastore.user there. */
import * as admin from "firebase-admin";
import { GoogleAuth } from "google-auth-library";
import {
  LiveDay,
  LiveQuantities,
  LIVE_DOC_ID,
  liveDates,
  liveWindow,
  mergeLiveDoc,
  meteredUsd,
  parseLiveDoc,
} from "../../lib/wall-live";
import RATES from "../../lib/omi-tv-live-rates.json";

const PROJECT = "based-hardware";
const GMP_QUERY = `https://monitoring.googleapis.com/v1/projects/${PROJECT}/location/global/prometheus/api/v1/query`;
const MON_SERIES = `https://monitoring.googleapis.com/v3/projects/${PROJECT}/timeSeries`;
const COLLECTION = "admin_stats_payload_cache";
const auth = new GoogleAuth({
  scopes: ["https://www.googleapis.com/auth/monitoring.read"],
});

async function token(): Promise<string> {
  const client = await auth.getClient();
  const t = await client.getAccessToken();
  if (!t.token) throw new Error("monitoring token unavailable");
  return t.token;
}

async function getJson(url: string, bearer: string): Promise<unknown> {
  for (let attempt = 0; attempt < 3; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, {
        headers: { Authorization: `Bearer ${bearer}` },
        signal: AbortSignal.timeout(120_000),
      });
    } catch {
      if (attempt === 2) throw new Error("monitoring request failed");
      await new Promise((r) => setTimeout(r, 2000 * 2 ** attempt));
      continue;
    }
    if ([429, 500, 502, 503, 504].includes(response.status) && attempt < 2) {
      await new Promise((r) => setTimeout(r, 2000 * 2 ** attempt));
      continue;
    }
    // Status only: a Monitoring error body can echo request filters.
    if (!response.ok) throw new Error(`monitoring HTTP ${response.status}`);
    return response.json();
  }
  throw new Error("monitoring retry budget exceeded");
}

interface Series {
  labels: Record<string, string>;
  value: number;
}

/** Monitoring v3 time series summed over [start, end) (the prototype's `mon`). */
async function monitoringSeries(
  metric: string,
  start: number,
  end: number,
  bearer: string
): Promise<Series[]> {
  const params = new URLSearchParams({
    filter: `metric.type = "${metric}"`,
    "interval.startTime": new Date(start).toISOString(),
    "interval.endTime": new Date(end).toISOString(),
    "aggregation.alignmentPeriod": "3600s",
    "aggregation.perSeriesAligner": "ALIGN_SUM",
    pageSize: "3000",
  });
  const byKey = new Map<string, Series>();
  let pageToken: string | undefined;
  do {
    if (pageToken) params.set("pageToken", pageToken);
    const body = (await getJson(`${MON_SERIES}?${params}`, bearer)) as {
      timeSeries?: {
        resource?: { labels?: Record<string, string> };
        metric?: { labels?: Record<string, string> };
        points?: { value?: { int64Value?: string; doubleValue?: number } }[];
      }[];
      nextPageToken?: string;
    };
    for (const s of body.timeSeries ?? []) {
      const labels = { ...s.resource?.labels, ...s.metric?.labels };
      const key = JSON.stringify(Object.entries(labels).sort());
      const value = (s.points ?? []).reduce(
        (sum, p) =>
          sum + Number(p.value?.int64Value ?? p.value?.doubleValue ?? 0),
        0
      );
      const row = byKey.get(key) ?? { labels, value: 0 };
      row.value += value;
      byKey.set(key, row);
    }
    pageToken = body.nextPageToken;
  } while (pageToken);
  return [...byKey.values()];
}

/** Managed-Prometheus instant query at `at` (ms). */
async function gmpVector(
  query: string,
  at: number,
  bearer: string
): Promise<{ metric: Record<string, string>; value: number }[]> {
  const url = `${GMP_QUERY}?${new URLSearchParams({
    query,
    time: String(at / 1000),
  })}`;
  const body = (await getJson(url, bearer)) as {
    data?: {
      result?: { metric: Record<string, string>; value: [number, string] }[];
    };
  };
  return (body.data?.result ?? []).map((r) => ({
    metric: r.metric,
    value: Number(r.value[1]),
  }));
}

const READ_METHODS = new Set<string>(RATES.fsReadMethods);
const WRITE_METHODS = new Set<string>(RATES.fsWriteMethods);
const GCS_A_METHODS = new Set<string>(RATES.gcsAMethods);

/** Metered quantities for [start, end): Cloud Run instance-seconds (managed
 * Prometheus, `increase` over the window), Firestore requests by method,
 * GCS operations by class, and logging bytes ingested. */
export async function quantitiesFor(
  start: number,
  end: number,
  bearer: string
): Promise<LiveQuantities> {
  const windowSeconds = Math.round((end - start) / 1000);
  const cr = await gmpVector(
    `sum by (service_name) (increase(run_googleapis_com:container_billable_instance_time{monitored_resource="cloud_run_revision"}[${windowSeconds}s]))`,
    end,
    bearer
  );
  const crInstanceSeconds: Record<string, number> = {};
  for (const r of cr)
    crInstanceSeconds[r.metric.service_name ?? "unknown"] = r.value;

  let fsReads = 0;
  let fsWrites = 0;
  for (const s of await monitoringSeries(
    "firestore.googleapis.com/api/request_count",
    start,
    end,
    bearer
  )) {
    if (!("database_id" in s.labels)) continue;
    const method = s.labels.api_method ?? "";
    if (READ_METHODS.has(method)) fsReads += s.value;
    else if (WRITE_METHODS.has(method)) fsWrites += s.value;
  }

  let gcsA = 0;
  let gcsB = 0;
  for (const s of await monitoringSeries(
    "storage.googleapis.com/api/request_count",
    start,
    end,
    bearer
  )) {
    if ((s.labels.response_code ?? "").match(/^[45]/)) continue;
    if (GCS_A_METHODS.has(s.labels.method ?? "")) gcsA += s.value;
    else gcsB += s.value;
  }

  let logBytes = 0;
  for (const s of await monitoringSeries(
    "logging.googleapis.com/billing/bytes_ingested",
    start,
    end,
    bearer
  ))
    logBytes += s.value;

  return { crInstanceSeconds, fsReads, fsWrites, gcsA, gcsB, logBytes };
}

async function writeDoc(produced: LiveDay[], now: number) {
  if (!admin.apps.length) admin.initializeApp({ projectId: PROJECT });
  const db = admin.firestore();
  const ref = db.collection(COLLECTION).doc(LIVE_DOC_ID);
  await db.runTransaction(async (t) => {
    const snap = await t.get(ref);
    const stored = snap.exists
      ? parseLiveDoc(JSON.parse(String(snap.data()?.payload ?? "null")))
      : null;
    t.set(ref, {
      payload: JSON.stringify(mergeLiveDoc(stored, produced, now)),
      freshAt: now,
    });
  });
}

export async function main(now = Date.now()) {
  const bearer = await token();
  const produced: LiveDay[] = [];
  for (const date of liveDates(now)) {
    const window = liveWindow(date, now);
    if (!window) continue;
    const quantities = await quantitiesFor(window.start, window.end, bearer);
    produced.push({
      date,
      queryEnd: new Date(window.end).toISOString(),
      fraction: window.fraction,
      metered: meteredUsd(quantities),
      producedAt: new Date(now).toISOString(),
    });
  }
  if (!produced.length) return;
  await writeDoc(produced, now);
  // Totals and dates only: no account, query or response detail.
  console.info(
    JSON.stringify({
      event: "wall_live_run",
      outcome: "written",
      days: produced.map((d) => ({
        date: d.date,
        fraction: Math.round(d.fraction * 10000) / 10000,
        meteredUsd: Math.round(
          d.metered.cloudRun +
            d.metered.firestore +
            d.metered.gcs +
            d.metered.logging
        ),
      })),
    })
  );
}
