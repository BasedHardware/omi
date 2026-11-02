import {
  interpretAggregateResponse,
  type AggregateInterpretation,
  type TelemetryQueryChannel,
} from "@/lib/telemetry/aggregates";

/**
 * Server-side privileged read of GET /v1/telemetry/client/aggregates.
 * Uses the admin dashboard's existing X-Admin-Key / X-Admin-User gate after
 * requireScope. The browser Firebase token is never forwarded.
 *
 * Integration dependency: Lane 1 must accept this admin gate (the same one
 * feedback admin uses). Ordinary user auth is not sufficient.
 */
export async function fetchTelemetryAggregates({
  adminUid,
  days,
  channel,
  now = new Date(),
  fetchImpl = fetch,
}: {
  adminUid: string;
  days: number;
  channel: TelemetryQueryChannel;
  now?: Date;
  fetchImpl?: typeof fetch;
}): Promise<AggregateInterpretation> {
  const base = (process.env.NEXT_PUBLIC_OMI_API_URL ?? "").replace(/\/$/, "");
  const adminKey = process.env.OMI_API_SECRET_KEY ?? "";
  const safeDays = Math.min(Math.max(Math.trunc(days), 1), 90);
  if (!base || !adminKey || !adminUid) {
    return {
      disposition: "unavailable",
      usable: false,
      body: null,
      code: "telemetry_unavailable",
      countThrough: null,
    };
  }
  const url = `${base}/v1/telemetry/client/aggregates?days=${safeDays}&channel=${channel}`;
  try {
    const response = await fetchImpl(url, {
      method: "GET",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "X-Admin-Key": adminKey,
        "X-Admin-User": adminUid,
      },
    });
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    return interpretAggregateResponse({
      httpStatus: response.status,
      payload,
      now,
    });
  } catch (error) {
    console.error("Telemetry aggregate read failed", error);
    return {
      disposition: "unavailable",
      usable: false,
      body: null,
      code: "telemetry_unavailable",
      countThrough: null,
    };
  }
}
