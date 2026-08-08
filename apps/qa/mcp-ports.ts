// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-002)
// domain-pending(DIV-DOMX-006)
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { ApplicationReadDenied } from "../../core/retrieve/authorization-boundary";
import type { ContentSafeRecallTrace } from "../../core/retrieve/recall-integrity";
import { isInvalidMcpCursorError } from "../mcp/cursor";
import {
  SYNTHESIZED_MEMORY_READ_SCOPE,
  type AuthorizationDecision,
  type McpCredential,
  type McpProtocolPorts,
  type RateLimitDecision,
} from "../mcp/protocol";
import type { QaDevAuthRegistry, QaPrincipal } from "./dev-auth";
import type { QaRecallReader } from "./recall-service";

/**
 * QA implementation of the MCP protocol's dependency ports.
 *
 * The transport owns none of this: authentication, authorization, rate limiting,
 * page reading, contract validation, and the final revocation fence are all
 * supplied here. This module selects no production identity provider, rate-limit
 * policy, or origin allow-list.
 */

export interface QaMcpPortsOptions {
  readonly registry: QaDevAuthRegistry;
  readonly principal: QaPrincipal;
  readonly reader: QaRecallReader;
  /**
   * Exact origins permitted for this loopback surface, resolved per request.
   * A thunk rather than an array because the listening port is not known until
   * after the server binds, and the origin allow-list must name the real port
   * rather than a guess.
   */
  readonly allowed_origins: () => readonly string[];
  /** Records what the default telemetry path would emit. Proof-4 evidence. */
  readonly telemetrySink?: (event: Readonly<Record<string, unknown>>) => void;
}

export interface QaMcpPortsHandle {
  readonly ports: McpProtocolPorts;
  readonly counters: () => Readonly<Record<string, number>>;
  readonly emittedTraces: () => readonly ContentSafeRecallTrace[];
}

const isSamePrincipal = (credential: McpCredential, principal: QaPrincipal): boolean =>
  credential.rateLimitKey.uid === principal.owner_account_id
  && credential.rateLimitKey.app_id === principal.app_id
  && credential.rateLimitKey.key_id === principal.key_id;

export const createQaMcpPorts = (options: QaMcpPortsOptions): QaMcpPortsHandle => {
  const { registry, principal, reader, allowed_origins: allowedOrigins, telemetrySink } = options;
  const traces: ContentSafeRecallTrace[] = [];
  const counters: Record<string, number> = {
    validateOrigin: 0, authenticate: 0, authorize: 0, rateLimit: 0,
    readPage: 0, validatePage: 0, reauthorize: 0, reauthorizeDenied: 0,
  };

  /**
   * The live authorization predicate, evaluated from the registry every time.
   * Both `authorize` (before the read) and `reauthorizeBeforeEmission` (after the
   * bytes exist, before they leave) call this, which is what makes the second one
   * a real fence rather than a repeat of a cached answer.
   */
  const currentlyAuthorized = (credential: McpCredential): boolean => {
    if (!isSamePrincipal(credential, principal)) return false;
    if (!credential.scopes.includes(SYNTHESIZED_MEMORY_READ_SCOPE)) return false;
    const resolved = registry.resolveCredential(principal);
    if (!resolved.active || !resolved.scopes.includes(SYNTHESIZED_MEMORY_READ_SCOPE)) return false;
    const grant = registry.resolveGrant(principal);
    return grant !== null
      && grant.enabled
      && grant.default_read
      && grant.scopes.includes(SYNTHESIZED_MEMORY_READ_SCOPE);
  };

  const ports: McpProtocolPorts = {
    validateOrigin: (input) => {
      counters.validateOrigin += 1;
      return allowedOrigins().includes(input.origin);
    },

    authenticate: async (input) => {
      counters.authenticate += 1;
      return registry.authenticate(input.apiKeyHeader);
    },

    authorize: async (input): Promise<AuthorizationDecision> => {
      counters.authorize += 1;
      if (!currentlyAuthorized(input.credential)) {
        return { allowed: false };
      }
      // A non-empty plain-JSON record: the protocol rejects an empty or
      // non-JSON readAuthorization as "not a real authorization".
      return {
        allowed: true,
        readAuthorization: {
          owner_account_id: principal.owner_account_id,
          app_id: principal.app_id,
          key_id: principal.key_id,
          scope: SYNTHESIZED_MEMORY_READ_SCOPE,
        },
      };
    },

    /**
     * QA rate limiting is intentionally permissive and hermetic: a real limiter
     * needs a clock and a shared counter store, and which one is a production
     * decision item. It still returns the exact decision shape so the transport's
     * ring is exercised.
     */
    rateLimit: async (): Promise<RateLimitDecision> => {
      counters.rateLimit += 1;
      return { allowed: true };
    },

    readPage: async (input) => {
      counters.readPage += 1;
      try {
        const result = await reader.readPage({
          limit: input.limit,
          cursor: input.cursor,
        });
        return { canonical_json: result.canonical_json };
      } catch (error) {
        // An invalid cursor is client input and keeps its own public shape, which
        // the transport turns into one invalid-cursor response.
        if (isInvalidMcpCursorError(error)) throw error;
        // A denial that lands mid-read must emit nothing. It deliberately does
        // NOT become an invalid-cursor response: that would tell an unauthorized
        // caller that their cursor was the problem, which is an oracle.
        if (error instanceof ApplicationReadDenied) {
          throw new Error("read denied");
        }
        throw error;
      }
    },

    /**
     * The fail-closed wire boundary. The bytes are re-parsed with the ratified
     * parser here, so a page that cannot be represented by the contract never
     * reaches a client even though the read core already produced it.
     */
    validatePage: (page) => {
      counters.validatePage += 1;
      if (page === null || typeof page !== "object") return null;
      const canonical = (page as { canonical_json?: unknown }).canonical_json;
      if (typeof canonical !== "string") return null;
      return parseSynthesizedPageJson(canonical) === null ? null : canonical;
    },

    reauthorizeBeforeEmission: async (input) => {
      counters.reauthorize += 1;
      const allowed = currentlyAuthorized(input.credential);
      if (!allowed) counters.reauthorizeDenied += 1;
      return allowed;
    },
  };

  return Object.freeze({
    ports,
    counters: () => Object.freeze({ ...counters }),
    emittedTraces: () => Object.freeze([...traces]),
  });
};

/**
 * Default telemetry for a QA request.
 *
 * Everything here is a reference, a count, or an enum. No query, memory,
 * evidence, source content, synthesized text, or raw identifier is admitted --
 * and the proof asserts that on the emitted bytes rather than trusting this
 * comment.
 */
export const qaRequestTelemetry = (input: {
  readonly method: string;
  readonly status: number;
  readonly outcome: "ok" | "denied" | "invalid_cursor" | "error";
  readonly item_count: number;
  readonly has_more: boolean;
}): Readonly<Record<string, unknown>> => Object.freeze({
  event: "qa.mcp.request",
  method: input.method,
  status: input.status,
  outcome: input.outcome,
  item_count: input.item_count,
  has_more: input.has_more,
});
