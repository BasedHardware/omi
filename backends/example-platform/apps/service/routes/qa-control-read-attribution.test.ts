import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createLocalDevService, type LocalService } from "../app-facing";

const CLIENT_ID_HEADER = "x-omi-client-id";
const UNATTRIBUTED_RUN = "__unattributed__";

interface Booted {
  readonly service: LocalService;
  readonly authorization: string;
}

const boot = (): Booted => {
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: "local-dev-user",
    memoryCount: 3,
    accountTimezone: "America/Los_Angeles",
    devSecretLabel: "omi-local-dev-token-not-a-secret-v1",
  });
  return { service, authorization: `Bearer ${service.devToken}` };
};

const read = (booted: Booted, clientId?: string): Promise<Response> => {
  const headers: Record<string, string> = { authorization: booted.authorization };
  if (clientId !== undefined) headers[CLIENT_ID_HEADER] = clientId;
  return booted.service.app.request("/v1/memories?limit=1", { headers });
};

const stats = async (booted: Booted, suffix: string): Promise<Record<string, unknown>> =>
  (await (await booted.service.app.request(`/v1/qa/control/stats${suffix}`)).json()) as Record<string, unknown>;

describe("per-run served-read attribution at the registered QA join endpoint", () => {
  test("concurrent runs see only their own served reads and unattributed traffic has one reserved bucket", async () => {
    const booted = boot();
    const left = `left-${crypto.randomUUID()}`;
    const right = `right-${crypto.randomUUID()}`;

    const responses = await Promise.all([
      read(booted, left),
      read(booted, right),
      read(booted, right),
      read(booted),
      read(booted, left),
      read(booted, right),
    ]);
    expect(responses.map((response) => response.status)).toEqual([200, 200, 200, 200, 200, 200]);

    expect(await stats(booted, `?run=${encodeURIComponent(left)}`)).toMatchObject({
      run: left,
      requestedRun: left,
      normalised: false,
      reads: { served: 2 },
    });
    expect(await stats(booted, `?run=${encodeURIComponent(right)}`)).toMatchObject({
      run: right,
      requestedRun: right,
      normalised: false,
      reads: { served: 3 },
    });
    expect(await stats(booted, "")).toMatchObject({
      run: UNATTRIBUTED_RUN,
      requestedRun: "",
      normalised: true,
      reads: { served: 1 },
    });
  });

  test("absent, empty and whitespace client ids share the resolved unattributed bucket", async () => {
    const booted = boot();
    const responses = await Promise.all([
      read(booted),
      read(booted, ""),
      read(booted, "   "),
    ]);
    expect(responses.map((response) => response.status)).toEqual([200, 200, 200]);

    const spellings = await Promise.all([
      stats(booted, ""),
      stats(booted, "?run="),
      stats(booted, "?run=%20%20%20"),
    ]);
    expect(spellings.map((entry) => entry["run"])).toEqual([
      UNATTRIBUTED_RUN,
      UNATTRIBUTED_RUN,
      UNATTRIBUTED_RUN,
    ]);
    expect(spellings.map((entry) => entry["normalised"])).toEqual([true, true, true]);
    expect(spellings.map((entry) => entry["reads"])).toEqual([
      { served: 3 },
      { served: 3 },
      { served: 3 },
    ]);
  });
});
