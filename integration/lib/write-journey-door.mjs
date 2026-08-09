#!/usr/bin/env bun
// LIFECYCLE: permanent
//
// Process-only launcher for platform's registered app-facing composition.
// Routes, handlers, stores, tokens, counters and composition all come from
// `createLocalService`; this file contributes only fixture config and the
// loopback socket that dev-stack allocates to port 4851.

import { join } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_OWNER = "local-dev-user";
const DEFAULT_TIMEZONE = "America/Los_Angeles";
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";

export function readRegisteredDoorArgs(argv) {
  const value = (name, fallback = undefined) => {
    const index = argv.indexOf(name);
    return index === -1 ? fallback : argv[index + 1];
  };
  const platformRepo = value("--platform-repo");
  if (typeof platformRepo !== "string" || platformRepo === "") {
    throw new TypeError("--platform-repo is required");
  }

  const port = Number(value("--port", "4851"));
  if (!Number.isSafeInteger(port) || port < 0 || port > 65_535) {
    throw new TypeError(`--port must be an integer from 0 to 65535, got ${String(port)}`);
  }
  const memoryCount = Number(value("--seed", "7"));
  if (!Number.isSafeInteger(memoryCount) || memoryCount < 0) {
    throw new TypeError(`--seed must be a non-negative integer, got ${String(memoryCount)}`);
  }

  return Object.freeze({
    platformRepo,
    port,
    memoryCount,
    ownerAccountId: value("--owner", DEFAULT_OWNER),
    accountTimezone: value("--timezone", DEFAULT_TIMEZONE),
  });
}

export async function bootRegisteredDoor(config) {
  const appFacingUrl = pathToFileURL(join(config.platformRepo, "apps/service/app-facing.ts")).href;
  const loopbackUrl = pathToFileURL(join(config.platformRepo, "apps/service/net/loopback.ts")).href;
  const [{ Database }, { createLocalService }, { LOOPBACK_HOST }] = await Promise.all([
    import("bun:sqlite"),
    import(appFacingUrl),
    import(loopbackUrl),
  ]);

  const db = new Database(":memory:");
  const service = createLocalService({
    db,
    ownerAccountId: config.ownerAccountId,
    memoryCount: config.memoryCount,
    accountTimezone: config.accountTimezone,
    devSecretLabel: DEV_KEY_MATERIAL_LABEL,
  });
  const server = Bun.serve({
    hostname: LOOPBACK_HOST,
    port: config.port,
    fetch: service.app.fetch,
  });

  return Object.freeze({ db, service, server, url: `http://${LOOPBACK_HOST}:${server.port}` });
}

if (process.argv[1] && process.argv[1].endsWith("write-journey-door.mjs")) {
  try {
    const config = readRegisteredDoorArgs(process.argv.slice(2));
    const booted = await bootRegisteredDoor(config);
    process.stdout.write(`${JSON.stringify({
      event: "registered_door_listening",
      pid: process.pid,
      url: booted.url,
      devToken: booted.service.devToken,
      ownerAccountId: config.ownerAccountId,
      memoryCount: config.memoryCount,
    })}\n`);

    const stop = () => {
      booted.server.stop(true);
      booted.db.close();
      process.exit(0);
    };
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
  } catch (error) {
    process.stderr.write(`registered door failed to boot: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  }
}
