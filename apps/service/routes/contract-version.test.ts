// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { APP_CONTRACT_VERSION_HEADER } from "@omi-core/ratified-contracts/projections/synthesized";

import { createLocalDevService, type LocalService } from "../app-facing";

/**
 * COORD-contract-evolution-policy.md §4: every app-facing request declares
 * the contract version its client was built against; a request without one
 * is treated as the floor - never rejected. This is the route-level proof
 * that `GET /v1/memories` actually reads `x-omi-contract-version` end to
 * end through the real booted service (same factory `bin/dev-server.ts`
 * uses), not just the unit-level resolver in the vendored contract package.
 */

const OWNER_ACCOUNT_ID = "local-dev-user";
const MEMORY_COUNT = 3;
const ACCOUNT_TIMEZONE = "America/Los_Angeles";
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";

const bootService = (): LocalService =>
  createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: MEMORY_COUNT,
    accountTimezone: ACCOUNT_TIMEZONE,
    devSecretLabel: DEV_KEY_MATERIAL_LABEL,
  });

const requestMemories = (service: LocalService, headers: Record<string, string>): Request =>
  new Request("http://contract-version.invalid/v1/memories", {
    method: "GET",
    headers: { authorization: `Bearer ${service.devToken}`, ...headers },
  });

describe("app-facing contract version declaration", () => {
  test("a request with no declared-version header is served normally and counted at the floor", async () => {
    const service = bootService();
    const response = await service.app.fetch(requestMemories(service, {}));

    expect(response.status).toBe(200);
    const snap = service.counter.snapshot();
    // red-proof: swap which branch increments in memories.ts's
    // recordDeclaredContractVersion({ atFloor: ... }) call and this fails -
    // an absent header would count as "explicit" instead of "at floor".
    expect(snap.declaredContractVersionAtFloor).toBe(1);
    expect(snap.declaredContractVersionExplicit).toBe(0);
  });

  test("a well-formed declared-version header is served normally and counted as explicit", async () => {
    const service = bootService();
    const response = await service.app.fetch(
      requestMemories(service, { [APP_CONTRACT_VERSION_HEADER]: "9.9.9" }),
    );

    expect(response.status).toBe(200);
    const snap = service.counter.snapshot();
    expect(snap.declaredContractVersionAtFloor).toBe(0);
    expect(snap.declaredContractVersionExplicit).toBe(1);
  });

  test("a malformed declared-version header is TOLERATED, not rejected, and counted at the floor", async () => {
    // COORD-contract-evolution-policy.md §4's tolerate-and-count rule, proven
    // at the route: garbage input must never turn into a 400/401/403 - it
    // must behave exactly like an absent header.
    const service = bootService();
    const withHeader = await service.app.fetch(
      requestMemories(service, { [APP_CONTRACT_VERSION_HEADER]: "not-a-real-version" }),
    );
    const withoutHeader = await service.app.fetch(requestMemories(service, {}));

    expect(withHeader.status).toBe(200);
    // red-proof: reject a malformed header with 400 instead of tolerating it
    // and this fails on the status-equality assertion below.
    expect(withHeader.status).toBe(withoutHeader.status);
    const snap = service.counter.snapshot();
    expect(snap.declaredContractVersionAtFloor).toBe(2);
    expect(snap.declaredContractVersionExplicit).toBe(0);
  });

  test("declaring a contract version never changes the served response bytes (purely additive)", async () => {
    const service = bootService();
    const withoutHeader = await service.app.fetch(requestMemories(service, {}));
    const bodyWithoutHeader = await withoutHeader.text();
    const withHeader = await service.app.fetch(
      requestMemories(service, { [APP_CONTRACT_VERSION_HEADER]: "1.0.0" }),
    );
    const bodyWithHeader = await withHeader.text();

    // red-proof: branch the response body on the declared header and this
    // fails - the classification rule for `additive` requires every client
    // built against a prior version to keep working unchanged.
    expect(bodyWithHeader).toBe(bodyWithoutHeader);
  });
});
