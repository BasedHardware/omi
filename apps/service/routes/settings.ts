// domain-pending(UNK-DOMAPPS-001)
import type { Hono } from "hono";

import {
  APP_CONTRACT_VERSION_HEADER,
  isWellFormedContractVersion,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import type { DevPrincipal } from "../auth/dev-token";
import type { SettingsProjectionReader } from "../control/settings-projection";
import type { ServedCounter } from "../observability/served-count";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const UNAVAILABLE_HEADERS = Object.freeze({
  ...JSON_HEADERS,
  "retry-after": "60",
});

const SIGNED_OUT_BODY = JSON.stringify({ identity: null, entitlement: null });
const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const FORBIDDEN_BODY = JSON.stringify({ error: "forbidden" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });
const UNAVAILABLE_BODY = JSON.stringify({ error: "service_unavailable" });

export const SETTINGS_PATH = "/v1/settings";

export interface SettingsRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly projections: SettingsProjectionReader;
  readonly counter: ServedCounter;
}

const response = (
  body: string,
  status: number,
  headers: Readonly<Record<string, string>> = JSON_HEADERS,
): Response => new Response(body, { status, headers });

const bearerToken = (presentHeader: string): string | null => {
  if (!presentHeader.startsWith("Bearer ")) return null;
  const token = presentHeader.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const hasInvalidRequestGrammar = (request: Request): boolean => {
  let url: URL;
  try {
    url = new URL(request.url);
  } catch {
    return true;
  }
  if ([...url.searchParams].length > 0) return true;
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null && contentLength !== "0") return true;
  return request.headers.has("transfer-encoding");
};

const recordContractVersion = (
  header: string | undefined,
  counter: ServedCounter,
): void => {
  counter.recordDeclaredContractVersion({
    atFloor: typeof header !== "string" || !isWellFormedContractVersion(header.trim()),
  });
  void resolveDeclaredContractVersion(header);
};

/** One optional-auth read; absent and invalid credentials are separate branches. */
export const registerSettingsRoutes = (app: Hono, deps: SettingsRouteDependencies): void => {
  app.get(SETTINGS_PATH, (context) => {
    if (hasInvalidRequestGrammar(context.req.raw)) {
      deps.counter.recordDomainRead("denied");
      return response(BAD_REQUEST_BODY, 400);
    }

    recordContractVersion(
      context.req.header(APP_CONTRACT_VERSION_HEADER),
      deps.counter,
    );

    const authorization = context.req.header("authorization");
    if (authorization === undefined) {
      deps.counter.recordDomainRead("served");
      return response(SIGNED_OUT_BODY, 200);
    }

    const token = bearerToken(authorization);
    if (token === null) {
      deps.counter.recordDomainRead("denied");
      return response(UNAUTHORIZED_BODY, 401);
    }
    const principal = deps.resolvePrincipal(token);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return response(UNAUTHORIZED_BODY, 401);
    }

    try {
      const projection = deps.projections.readSettings(principal.uid);
      if (projection.status === "forbidden") {
        deps.counter.recordDomainRead("denied");
        return response(FORBIDDEN_BODY, 403);
      }
      if (projection.status === "unavailable") {
        deps.counter.recordDomainRead("failed");
        return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
      }
      deps.counter.recordDomainRead("served");
      return response(JSON.stringify(projection.snapshot), 200);
    } catch {
      deps.counter.recordDomainRead("failed");
      return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
    }
  });
};
