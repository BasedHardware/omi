/**
 * The injected HTTP seam — a pure declaration, so it lives here rather than in
 * the adapter package that used to own it.
 *
 * Placement: top-level, NOT under `bridge/`. This seam is transport-neutral —
 * the privileged bridge binds it, the DEV harness binds a direct fetch, tests
 * bind a script, and a future desktop shell binds its own net module.
 * `bridge/http.ts` is ONE implementation contract for crossing the bridge;
 * putting the seam itself in there would imply the bridge owns it. So it sits
 * beside the other cross-cutting declarations (`errors.ts`, `ids.ts`,
 * `snapshot.ts`).
 *
 * Adapters never construct absolute URLs and never touch tokens — auth and the
 * base URL are the transport binding's job (ADR-008 §3 / ADR-009 §3).
 *
 * The status → taxonomy mapping (`classifyStatus`) is executable, so it cannot
 * live here (nothing in `contracts/` executes). It lives in `@omi-core/kernel`.
 */

export interface HttpResponse {
  status: number;
  /** Parsed JSON body, or null when the body was empty/unparseable. */
  json: unknown;
  /**
   * The RAW response body, exactly as received, when the binding can supply it.
   *
   * Optional and additive: every existing binding and every existing adapter
   * keeps working without it, so this is not a breaking contract change and
   * does not bump `BRIDGE_CONTRACT_VERSION`.
   *
   * It exists because a pre-parsed `json` is a lossy boundary for a contract
   * whose validator is defined over the BYTES. `@omi-core/ratified-contracts`
   * makes this explicit: `parseSynthesizedPageJson(raw: string)` is documented
   * as "the authoritative no-execution boundary for untrusted canonical JSON
   * text" — it rejects noncanonical encodings, duplicate keys, oversized
   * payloads, and normalized escapes/numbers before the contract predicate
   * ever runs. Its object-level sibling `isTrustedSynthesizedPageData` is
   * documented, in the same package, as "NOT a hostile-object boundary", and a
   * duplicate-key payload is already indistinguishable once `JSON.parse` has
   * kept only the last value.
   *
   * So a binding that CAN hand over the raw body should, and an adapter that
   * has one should prefer the text parser. An adapter must still work without
   * it — see `fetchSynthesizedMemoryPage`, which reports WHICH boundary it
   * used rather than pretending the two are equivalent.
   */
  text?: string;
  /** Retry-After in milliseconds when the server sent one. */
  retryAfterMs?: number;
}

export interface HttpClient {
  request(method: "GET" | "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<HttpResponse>;
}
