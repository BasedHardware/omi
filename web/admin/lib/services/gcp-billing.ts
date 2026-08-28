import { BigQuery } from "@google-cloud/bigquery";

// Daily net GCP spend from the BigQuery billing export.
//
// Method follows the cost-monitoring contract established in the
// gcp-cost-efficiency knowledge-base project:
//   - net = cost + credits (gross alone overstates; promo/committed-use
//     credits are real money not spent),
//   - filter on _PARTITIONTIME (ingestion partition) so queries don't scan
//     the whole table — a bare usage_start_time filter does,
//   - the export lags ~11h and back-fills for up to two days, so the series
//     ends at D-2; later days would silently under-report and hide ramps.
//
// Credentials: GCP_BILLING_SA_JSON (service-account JSON string) or ambient
// ADC. The Firebase admin SA is NOT assumed to have BigQuery access.

const DEFAULT_BILLING_TABLE =
  "based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256";

// Services whose spend is LLM inference (split by the LLM usage mix rather
// than the general activity mix downstream).
const LLM_SERVICE_PATTERN = /vertex|gemini|generative/i;

export interface GcpDailyCost {
  date: string; // YYYY-MM-DD (UTC usage day)
  netUsd: number;
  grossUsd: number;
  llmNetUsd: number; // Vertex/Gemini portion of netUsd
}

export interface GcpServiceCost {
  service: string;
  netUsd: number;
  isLlm: boolean;
}

export interface GcpBillingSnapshot {
  daily: GcpDailyCost[];
  services: GcpServiceCost[]; // totals over the same window
  windowStart: string;
  windowEnd: string; // inclusive; always D-2 or older
}

let client: BigQuery | null = null;

function getClient(): BigQuery | null {
  if (client) return client;
  const raw = process.env.GCP_BILLING_SA_JSON;
  try {
    if (raw) {
      const sa = JSON.parse(raw);
      client = new BigQuery({
        projectId: sa.project_id,
        credentials: { client_email: sa.client_email, private_key: sa.private_key },
      });
    } else {
      client = new BigQuery(); // ADC (local dev / explicitly-granted runtime SA)
    }
    return client;
  } catch (err) {
    console.error("GCP billing client init failed:", err);
    return null;
  }
}

export function billingTable(): string {
  return process.env.GCP_BILLING_TABLE || DEFAULT_BILLING_TABLE;
}

// Exported for tests.
export function isLlmService(service: string): boolean {
  return LLM_SERVICE_PATTERN.test(service);
}

export async function fetchGcpBilling(days: number): Promise<GcpBillingSnapshot | null> {
  const bq = getClient();
  if (!bq) return null;

  // Inclusive end at D-2; start so the series still spans `days` days.
  const query = `
    SELECT
      FORMAT_DATE('%F', DATE(usage_start_time)) AS day,
      service.description AS service,
      ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 2) AS net_usd,
      ROUND(SUM(cost), 2) AS gross_usd
    FROM \`${billingTable()}\`
    WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @scanDays DAY)
      AND usage_start_time >= TIMESTAMP_SUB(TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY), INTERVAL @windowDays DAY)
      AND usage_start_time < TIMESTAMP_SUB(TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY), INTERVAL 1 DAY)
    GROUP BY day, service
  `;
  try {
    const [rows] = await bq.query({
      query,
      params: { scanDays: days + 7, windowDays: days + 1 },
      location: "US",
    });

    const dailyMap = new Map<string, GcpDailyCost>();
    const serviceMap = new Map<string, GcpServiceCost>();
    for (const row of rows as { day: string; service: string; net_usd: number; gross_usd: number }[]) {
      const entry =
        dailyMap.get(row.day) ?? { date: row.day, netUsd: 0, grossUsd: 0, llmNetUsd: 0 };
      entry.netUsd += row.net_usd;
      entry.grossUsd += row.gross_usd;
      const llm = isLlmService(row.service);
      if (llm) entry.llmNetUsd += row.net_usd;
      dailyMap.set(row.day, entry);

      const svc = serviceMap.get(row.service) ?? { service: row.service, netUsd: 0, isLlm: llm };
      svc.netUsd += row.net_usd;
      serviceMap.set(row.service, svc);
    }
    const daily = Array.from(dailyMap.values()).sort((a, b) => a.date.localeCompare(b.date));
    if (daily.length === 0) return null;
    const round = (v: number) => Math.round(v * 100) / 100;
    for (const d of daily) {
      d.netUsd = round(d.netUsd);
      d.grossUsd = round(d.grossUsd);
      d.llmNetUsd = round(d.llmNetUsd);
    }
    const services = Array.from(serviceMap.values())
      .map((s) => ({ ...s, netUsd: round(s.netUsd) }))
      .sort((a, b) => b.netUsd - a.netUsd);
    return {
      daily,
      services,
      windowStart: daily[0].date,
      windowEnd: daily[daily.length - 1].date,
    };
  } catch (err) {
    console.error("GCP billing query failed:", err);
    return null;
  }
}
