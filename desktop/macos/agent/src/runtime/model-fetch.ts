/** Request-scoped credentials only. No token cache, environment, or disk copy. */
export type ModelFailureCode = "authentication" | "quota_exceeded" | "transport_interruption" | "provider_setup_needed" | "unknown";
export type ModelHeadersReply = { headers?: Record<string, string>; failureCode?: ModelFailureCode };
export type ProviderStatus = { type: "omi_provider_status"; failureCode?: ModelFailureCode; status?: number; requestId?: string };

export function providerFailureCode(status: number, byok: boolean): ModelFailureCode | undefined {
  if (status < 400) return undefined;
  if (status === 401) return byok ? "provider_setup_needed" : "authentication";
  if (status === 402 || status === 429) return "quota_exceeded";
  return "unknown";
}

export function credentialedModelFetch(options: {
  baseUrl: string;
  fetch: typeof fetch;
  headers: (forceRefresh: boolean, capabilityRef?: string) => Promise<ModelHeadersReply>;
  report: (status: ProviderStatus) => void;
}): typeof fetch {
  const base = new URL(options.baseUrl);
  return async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.origin !== base.origin || url.pathname !== `${base.pathname.replace(/\/$/, "")}/chat/completions`) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      if (init?.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
      if (headers.has("x-omi-local-capability")) {
        headers.delete("x-omi-local-capability");
        return options.fetch(input, { ...init, headers });
      }
      return options.fetch(input, init);
    }
    // Clone before the first send: a Request body is single-use. Replay is only
    // permitted before handing any response bytes to pi, and only once.
    const request = new Request(input, init);
    const replay = request.clone();
    const requestId = request.headers.get("x-omi-request-id") ?? undefined;
    const capabilityRef = request.headers.get("x-omi-local-capability") ?? undefined;
    const report = (status: ProviderStatus) => options.report({ ...status, ...(requestId ? { requestId } : {}) });
    for (let attempt = 0; attempt < 2; attempt++) {
      request.signal.throwIfAborted();
      const reply = await options.headers(attempt === 1, capabilityRef);
      request.signal.throwIfAborted();
      if (!reply.headers?.Authorization) {
        report({ type: "omi_provider_status", failureCode: reply.failureCode ?? "transport_interruption" });
        throw new Error("Omi model credentials unavailable");
      }
      const headers = new Headers(request.headers);
      // Never forward a stale provider header from an SDK retry or an ambient key.
      for (const key of [...headers.keys()]) {
        if (key === "authorization" || key === "x-omi-local-capability" || key.startsWith("x-byok-")) headers.delete(key);
      }
      for (const [key, value] of Object.entries(reply.headers)) headers.set(key, value);
      const byok = ["openrouter", "openai", "anthropic", "gemini"].some(key => headers.has(`x-byok-${key}`));
      let response: Response;
      try {
        response = await options.fetch(new Request(attempt === 0 ? request : replay, { headers, redirect: "error" }));
      } catch (error) {
        report({ type: "omi_provider_status", failureCode: "transport_interruption" });
        throw error;
      }
      if (response.status === 401 && !byok && attempt === 0) {
        await response.body?.cancel();
        continue;
      }
      report({ type: "omi_provider_status", status: response.status, failureCode: providerFailureCode(response.status, byok) });
      return response;
    }
    throw new Error("Unreachable model retry state");
  };
}
