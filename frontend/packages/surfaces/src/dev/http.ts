/**
 * DEV-ONLY HttpClient: direct fetch with a bearer token. Ship mode NEVER uses
 * this — privileged transport crosses the bridge (ADR-008 §3 / ADR-009 §3).
 * It exists so the surface is testable in a plain browser / dev webview
 * before the shells' bridge transports land. No endpoint paths live here;
 * adapters own paths — this only prefixes the base URL and adds auth.
 */

import type { HttpClient, HttpResponse } from "@omi-core/contracts";

export function devHttpClient(baseUrl: string, token: () => string): HttpClient {
  return {
    async request(method, path, body): Promise<HttpResponse> {
      try {
        const res = await fetch(baseUrl.replace(/\/$/, "") + path, {
          method,
          headers: {
            authorization: `Bearer ${token()}`,
            ...(body !== undefined ? { "content-type": "application/json" } : {}),
          },
          ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        });
        let json: unknown = null;
        try {
          json = await res.json();
        } catch {
          json = null;
        }
        const retryAfter = res.headers.get("retry-after");
        const base: HttpResponse = { status: res.status, json };
        return retryAfter ? { ...base, retryAfterMs: Number(retryAfter) * 1000 } : base;
      } catch {
        // Network failure → a status the classifier maps to retryable.
        return { status: 503, json: null };
      }
    },
  };
}
