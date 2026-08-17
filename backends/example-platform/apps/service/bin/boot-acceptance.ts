#!/usr/bin/env bun
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)

/**
 * Boot acceptance: spawn the real dev server on a real socket, drive it over
 * real HTTP, and emit a machine-readable JSON verdict.
 *
 * Exit 0 only when every check passes. Detail strings carry counts and status
 * words only — never tokens, ids, or memory text.
 */

import { join } from "node:path";

const VERDICT_VERSION = "boot-acceptance-v1";
const PORT = 4851;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const READY_MARKER = "omi local backend is up";
const READY_TIMEOUT_MS = 30_000;
const PAGE_LIMIT = 3;
const MAX_PAGES = 64;
const REPO_ROOT = join(import.meta.dir, "../../..");

type CheckStatus = "pass" | "fail";

type Check = {
  readonly name: string;
  readonly status: CheckStatus;
  readonly detail: string;
};

type Verdict = {
  readonly version: typeof VERDICT_VERSION;
  readonly port: number;
  readonly checks: readonly Check[];
  readonly servedCount: number;
  readonly verdict: CheckStatus;
};

type MemoriesPage = {
  readonly items: readonly { readonly id: string }[];
  readonly window: { readonly nextCursor: string | null };
};

const authHeader = (token: string): HeadersInit => ({
  authorization: `Bearer ${token}`,
});

const extractDevToken = (banner: string): string | null => {
  const match = banner.match(/TOKEN='([^']+)'/);
  if (match === null) return null;
  const token = match[1];
  return token.length > 0 ? token : null;
};

const parseMemoriesPage = (body: string): MemoriesPage | null => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const record = parsed as Record<string, unknown>;
  if (!Array.isArray(record.items)) return null;
  const items: { readonly id: string }[] = [];
  for (const item of record.items) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return null;
    const id = (item as Record<string, unknown>).id;
    if (typeof id !== "string" || id.length === 0) return null;
    items.push({ id });
  }
  const window = record.window;
  if (window === null || typeof window !== "object" || Array.isArray(window)) return null;
  const nextCursor = (window as Record<string, unknown>).nextCursor;
  if (!(nextCursor === null || typeof nextCursor === "string")) return null;
  return { items, window: { nextCursor } };
};

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

const failVerdict = (checks: readonly Check[], servedCount: number): Verdict =>
  Object.freeze({
    version: VERDICT_VERSION,
    port: PORT,
    checks,
    servedCount,
    verdict: "fail" as const,
  });

async function waitForReady(
  getBuffer: () => string,
  isAlive: () => boolean,
): Promise<{ readonly ok: true; readonly token: string } | { readonly ok: false; readonly detail: string }> {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const buffer = getBuffer();
    if (buffer.includes(READY_MARKER)) {
      const token = extractDevToken(buffer);
      if (token !== null) return { ok: true, token };
    }
    if (!isAlive()) {
      return { ok: false, detail: "child exited before ready" };
    }
    await sleep(50);
  }
  if (!getBuffer().includes(READY_MARKER)) {
    return { ok: false, detail: "ready timeout" };
  }
  return { ok: false, detail: "token missing from banner" };
}

async function killChild(proc: ReturnType<typeof Bun.spawn>): Promise<void> {
  try {
    proc.kill("SIGTERM");
  } catch {
    // already gone
  }
  const exited = await Promise.race([
    proc.exited.then(() => true),
    sleep(2_000).then(() => false),
  ]);
  if (!exited) {
    try {
      proc.kill("SIGKILL");
    } catch {
      // already gone
    }
    await proc.exited;
  }
}

async function runChecks(token: string): Promise<Verdict> {
  const checks: Check[] = [{ name: "boot", status: "pass", detail: "ready" }];
  let servedCount = 0;
  let successfulDomainRequests = 0;

  // a. GET /health -> 200
  {
    const response = await fetch(`${BASE_URL}/health`);
    await response.arrayBuffer();
    const pass = response.status === 200;
    checks.push({
      name: "health",
      status: pass ? "pass" : "fail",
      detail: pass ? "status 200" : `status ${response.status}`,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // b. GET /v1/memories with NO auth -> 401
  {
    const response = await fetch(`${BASE_URL}/v1/memories`);
    await response.arrayBuffer();
    const pass = response.status === 401;
    checks.push({
      name: "memories-unauth",
      status: pass ? "pass" : "fail",
      detail: pass ? "status 401" : `status ${response.status}`,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // c. GET /v1/memories?limit=3 with token -> 200, non-empty items
  let firstPageBody = "";
  let nextCursor: string | null = null;
  const seenIds = new Set<string>();
  {
    const response = await fetch(`${BASE_URL}/v1/memories?limit=${PAGE_LIMIT}`, {
      headers: authHeader(token),
    });
    const body = await response.text();
    const page = response.status === 200 ? parseMemoriesPage(body) : null;
    const nonEmpty = page !== null && page.items.length > 0;
    const pass = response.status === 200 && nonEmpty;
    if (pass && page !== null) {
      successfulDomainRequests += 1;
      firstPageBody = body;
      nextCursor = page.window.nextCursor;
      for (const item of page.items) seenIds.add(item.id);
    }
    checks.push({
      name: "memories-page1",
      status: pass ? "pass" : "fail",
      detail: pass
        ? `status 200 items ${page!.items.length}`
        : response.status !== 200
        ? `status ${response.status}`
        : page === null
        ? "unparseable body"
        : "empty items",
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // d. Walk pagination; assert disjoint ids and termination
  {
    let pages = 1;
    let duplicate = false;
    let unparseable = false;
    let unterminated = false;
    let badStatus = 0;

    while (nextCursor !== null) {
      if (pages >= MAX_PAGES) {
        unterminated = true;
        break;
      }
      const url = new URL(`${BASE_URL}/v1/memories`);
      url.searchParams.set("limit", String(PAGE_LIMIT));
      url.searchParams.set("cursor", nextCursor);
      const response = await fetch(url, { headers: authHeader(token) });
      const body = await response.text();
      if (response.status !== 200) {
        badStatus = response.status;
        break;
      }
      const page = parseMemoriesPage(body);
      if (page === null) {
        unparseable = true;
        break;
      }
      successfulDomainRequests += 1;
      pages += 1;
      for (const item of page.items) {
        if (seenIds.has(item.id)) {
          duplicate = true;
          break;
        }
        seenIds.add(item.id);
      }
      if (duplicate) break;
      nextCursor = page.window.nextCursor;
    }

    let detail = `pages ${pages} items ${seenIds.size}`;
    let pass = true;
    if (badStatus !== 0) {
      pass = false;
      detail = `status ${badStatus}`;
    } else if (unparseable) {
      pass = false;
      detail = "unparseable page";
    } else if (duplicate) {
      pass = false;
      detail = "duplicate ids across pages";
    } else if (unterminated) {
      pass = false;
      detail = `unterminated after ${MAX_PAGES} pages`;
    }

    checks.push({
      name: "memories-pagination",
      status: pass ? "pass" : "fail",
      detail,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // e. The newly served conversations domain uses the same real listener.
  {
    const response = await fetch(`${BASE_URL}/v1/conversations?limit=1&offset=0`, {
      headers: authHeader(token),
    });
    const value = await response.json().catch(() => null) as unknown;
    const pass = response.status === 200 && Array.isArray(value) && value.length === 1;
    if (pass) successfulDomainRequests += 1;
    checks.push({
      name: "conversations-page1",
      status: pass ? "pass" : "fail",
      detail: pass ? "status 200 items 1" : `status ${response.status}`,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // f. GET /v1/qa/status — central check
  {
    const response = await fetch(`${BASE_URL}/v1/qa/status`);
    const body = await response.text();
    let detail = `status ${response.status}`;
    let pass = false;
    if (response.status === 200) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(body);
      } catch {
        parsed = null;
      }
      const served =
        parsed !== null
        && typeof parsed === "object"
        && !Array.isArray(parsed)
        && typeof (parsed as { served?: { domainReadsServed?: unknown } }).served
            ?.domainReadsServed === "number"
          ? (parsed as { served: { domainReadsServed: number } }).served.domainReadsServed
          : null;
      if (served === null) {
        detail = "unparseable status";
      } else {
        servedCount = served;
        if (served <= 0) {
          detail = `served count ${served} expected greater than zero`;
        } else if (served !== successfulDomainRequests) {
          detail = `served count ${served} expected ${successfulDomainRequests}`;
        } else {
          pass = true;
          detail = `served count ${served}`;
        }
      }
    }
    checks.push({
      name: "qa-served-count",
      status: pass ? "pass" : "fail",
      detail,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // g. POST /v1/qa/reset -> 200, then page 1 byte-identical to first page-1 body
  {
    const resetResponse = await fetch(`${BASE_URL}/v1/qa/reset`, {
      method: "POST",
      headers: authHeader(token),
    });
    await resetResponse.arrayBuffer();
    if (resetResponse.status !== 200) {
      checks.push({
        name: "qa-reset",
        status: "fail",
        detail: `status ${resetResponse.status}`,
      });
      return failVerdict(checks, servedCount);
    }

    const pageResponse = await fetch(`${BASE_URL}/v1/memories?limit=${PAGE_LIMIT}`, {
      headers: authHeader(token),
    });
    const pageBody = await pageResponse.text();
    const pass = pageResponse.status === 200 && pageBody === firstPageBody;
    checks.push({
      name: "qa-reset",
      status: pass ? "pass" : "fail",
      detail: pass
        ? "reset total"
        : pageResponse.status !== 200
        ? `status ${pageResponse.status}`
        : "page1 not identical after reset",
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  // h. Loopback proof via the existing assert-loopback script
  {
    const loopback = Bun.spawnSync(
      ["bun", "run", "apps/service/net/assert-loopback.ts", String(PORT)],
      {
        cwd: REPO_ROOT,
        stdout: "pipe",
        stderr: "pipe",
      },
    );
    const raw = loopback.stdout.toString("utf8").trim();
    let pass = false;
    let detail = "loopback invoke failed";
    if (raw.length > 0) {
      try {
        const parsed = JSON.parse(raw) as { verdict?: unknown };
        if (parsed.verdict === "pass") {
          pass = true;
          detail = "loopback pass";
        } else if (parsed.verdict === "fail") {
          detail = "loopback fail";
        } else if (parsed.verdict === "inconclusive") {
          detail = "loopback inconclusive";
        } else {
          detail = "loopback unparseable";
        }
      } catch {
        detail = "loopback unparseable";
      }
    }
    checks.push({
      name: "loopback",
      status: pass ? "pass" : "fail",
      detail,
    });
    if (!pass) return failVerdict(checks, servedCount);
  }

  return Object.freeze({
    version: VERDICT_VERSION,
    port: PORT,
    checks,
    servedCount,
    verdict: "pass" as const,
  });
}

async function main(): Promise<void> {
  const proc = Bun.spawn(
    ["bun", "run", "apps/service/bin/dev-server.ts"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, OMI_PORT: String(PORT) },
      stdout: "pipe",
      stderr: "pipe",
      stdin: "ignore",
    },
  );

  let stdoutBuffer = "";
  const stdoutDrain = (async () => {
    const reader = proc.stdout.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        stdoutBuffer += decoder.decode(value, { stream: true });
      }
    } catch {
      // reader cancelled on shutdown
    }
  })();

  const stderrDrain = (async () => {
    const reader = proc.stderr.getReader();
    try {
      while (true) {
        const { done } = await reader.read();
        if (done) break;
      }
    } catch {
      // reader cancelled on shutdown
    }
  })();

  let verdict: Verdict = failVerdict(
    [{ name: "boot", status: "fail", detail: "not started" }],
    0,
  );

  try {
    const ready = await waitForReady(
      () => stdoutBuffer,
      () => proc.exitCode === null,
    );
    if (!ready.ok) {
      verdict = failVerdict(
        [{ name: "boot", status: "fail", detail: ready.detail }],
        0,
      );
    } else {
      verdict = await runChecks(ready.token);
    }
  } catch {
    verdict = failVerdict(
      [{ name: "boot", status: "fail", detail: "unexpected error" }],
      0,
    );
  } finally {
    await killChild(proc);
    await Promise.allSettled([stdoutDrain, stderrDrain]);
  }

  process.stdout.write(`${JSON.stringify(verdict)}\n`);
  process.exit(verdict.verdict === "pass" ? 0 : 1);
}

main();
