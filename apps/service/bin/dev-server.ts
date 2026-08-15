// domain-pending(DIV-DOMCORE-001)
import { Database } from "bun:sqlite";
import { writeFileSync } from "node:fs";

import { createLocalDevService } from "../app-facing";
import { appendRuntimeLog } from "../observability/runtime-log";
import {
  createGatewayChatGenerationSource,
  createGatewayRequiredChatGenerationSource,
} from "../chat/generation-source";
import {
  bootGatewayKind,
  bootGatewayModel,
  probeGatewayEngineIdentity,
} from "../chat/gateway-engine-identity";
import {
  DevSttConfigError,
  resolveDevSttConfig,
} from "../listen/mlx-whisper-boot";
import { createMlxWhisperTranscriptionSource } from "../listen/mlx-whisper-transcription-source";
import type { ChatGenerationLivenessPolicy } from "../chat/generation-supervisor";
import { createGetActionItemsToolLoop } from "../chat/action-items-tool";
import { createProductionGatewayToolLoop } from "../chat/gateway-tool-composition";
import { resolveDevGenerationLiveness } from "../chat/real-model-liveness";
import { LOOPBACK_HOST, assertPortInRange } from "../net/loopback";
import { isQaEvidenceRunId } from "../observability/producer-evidence";
import { QA_FIXTURE_TIME_ANCHOR_UTC } from "../qa/seed";
import {
  applyDemoPersonaSeed,
  DEMO_PERSONA_MEMORY_COUNT,
  parseSeedPersona,
} from "../qa/demo-persona";
import { QA_EVIDENCE_PATH } from "../routes/qa-evidence";
import { SCREEN_RETENTION_INTERVAL_MS } from "../screen/retention-worker";
import { createSqliteLocalServiceStores } from "../../../drivers/sqlite/service-stores";

/**
 * One-command local backend for testing a real macOS/iOS app against the new
 * service.
 *
 *   bun run apps/service/bin/dev-server.ts
 *
 * From a cold checkout, with zero required environment variables, this boots a
 * loopback-only HTTP service with deterministic seed data already loaded and
 * prints the base URL, the dev token, and the seed identity.
 *
 * This file owns ONLY process concerns - config, socket, printing, signals. The
 * routes and their wiring live in `../app-facing.ts` so that tests exercise the
 * same app this serves, rather than a lookalike that could agree with a wrong
 * binding.
 *
 * SQLite here is QA fixture storage only, never production authority. No
 * production store, cloud service, credential, or deployment topology is
 * selected by this file.
 */

/** Ports allocated to this agent by the board's port registry. */
const DEFAULT_PORT = 4851;

/**
 * Fixed, non-secret dev key material.
 *
 * NOT a credential. It signs dev tokens for a loopback-only service that serves
 * synthetic fixture data, and it is committed on purpose so a restart issues the
 * SAME token and an app under test keeps working without re-pairing. Override
 * with OMI_DEV_TOKEN_SECRET to rotate. A real deployment replaces the whole
 * dev-token seam, not this constant.
 */
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";

const DEFAULT_OWNER = "local-dev-user";
const DEFAULT_MEMORY_COUNT = 12;
const DEFAULT_TIMEZONE = "America/Los_Angeles";


const fail = (message: string, reason: string): never => {
  appendRuntimeLog({
    proc: "service",
    level: "error",
    event: "service.boot.refused",
    reason,
  });
  process.stderr.write(`\nomi dev-server: ${message}\n\n`);
  process.exit(1);
};

interface BootConfig {
  readonly port: number;
  readonly ownerAccountId: string;
  readonly memoryCount: number;
  readonly accountTimezone: string;
  readonly databasePath: string;
  readonly devSecretLabel: string;
  readonly runId: string | null;
  readonly readyRecordPath: string | null;
  readonly seedPersona: "demo" | null;
  readonly llmGateway: Readonly<{
    readonly url: string;
    readonly token: string;
    readonly laneId: string;
  }> | null;
  readonly generationLiveness: ChatGenerationLivenessPolicy | null;
  readonly stt: ReturnType<typeof resolveDevSttConfig>;
}

const readConfig = (): BootConfig => {
  const rawPort = process.env.OMI_PORT;
  let port = DEFAULT_PORT;
  if (rawPort !== undefined && rawPort.length > 0) {
    if (!/^[0-9]{2,5}$/.test(rawPort)) fail(`OMI_PORT must be a number, got "${rawPort}".`, "invalid_port");
    port = Number(rawPort);
  }
  try {
    assertPortInRange(port);
  } catch {
    fail(
      `port ${port} is not allocated to this service. Use one bounded app-facing port.`,
      "port_unallocated",
    );
  }

  const rawCount = process.env.OMI_SEED_MEMORIES;
  let memoryCount = DEFAULT_MEMORY_COUNT;
  if (rawCount !== undefined && rawCount.length > 0) {
    if (!/^[0-9]{1,4}$/.test(rawCount)) fail(`OMI_SEED_MEMORIES must be a number, got "${rawCount}".`, "invalid_seed_count");
    memoryCount = Number(rawCount);
  }

  let seedPersona: "demo" | null = null;
  try {
    seedPersona = parseSeedPersona(process.env.OMI_SEED_PERSONA);
  } catch (error) {
    fail(error instanceof Error ? error.message : "OMI_SEED_PERSONA is invalid.", "invalid_persona");
  }
  if (seedPersona === "demo") memoryCount = DEMO_PERSONA_MEMORY_COUNT;

  const accountTimezone = process.env.OMI_ACCOUNT_TIMEZONE || DEFAULT_TIMEZONE;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: accountTimezone }).format(0);
  } catch {
    fail(
      `OMI_ACCOUNT_TIMEZONE "${accountTimezone}" is not a valid IANA timezone. `
      + `Example: America/Los_Angeles. The zone is required because memories are `
      + `grouped into days in LOCAL time, so a UTC-only fixture drifts by host.`,
      "invalid_timezone",
    );
  }

  const rawRunId = process.env.OMI_RUN_ID;
  const rawReadyRecordPath = process.env.OMI_DEV_READY_RECORD;
  if ((rawRunId === undefined) !== (rawReadyRecordPath === undefined)) {
    fail("OMI_RUN_ID and OMI_DEV_READY_RECORD must be supplied together.", "run_id_ready_record_mismatch");
  }
  if (rawRunId !== undefined && !isQaEvidenceRunId(rawRunId)) {
    fail("OMI_RUN_ID must be a bounded, non-reserved QA run id.", "invalid_run_id");
  }
  if (rawReadyRecordPath !== undefined && rawReadyRecordPath.length === 0) {
    fail("OMI_DEV_READY_RECORD must be a non-empty host-owned path.", "empty_ready_record_path");
  }

  const gatewayUrl = process.env.OMI_LLM_GATEWAY_URL?.trim() ?? "";
  const gatewayToken = process.env.OMI_LLM_GATEWAY_SERVICE_TOKEN?.trim() ?? "";
  if ((gatewayUrl.length === 0) !== (gatewayToken.length === 0)) {
    fail("OMI_LLM_GATEWAY_URL and OMI_LLM_GATEWAY_SERVICE_TOKEN must be supplied together.", "gateway_config_incomplete");
  }
  const llmGateway = gatewayUrl.length === 0 ? null : Object.freeze({
    url: gatewayUrl,
    token: gatewayToken,
    laneId: process.env.OMI_LLM_GATEWAY_LANE?.trim() || "omi:auto:chat-agent",
  });

  // The default liveness policy (100ms to first event, 1s total) is sized for
  // the canned test gateway, which answers instantly. A real model does not:
  // measured against GLM-4.7 through integration/local-model-gateway.mjs, a
  // one-sentence question spent 280 reasoning tokens before its first
  // `delta.content`, and the generation-source only observes content deltas —
  // so every real-model generation finalized `generation_timeout` and chat
  // answered nothing. Real-model runs get real-model deadlines; the canned
  // default is untouched.
  const generationLiveness = resolveDevGenerationLiveness(process.env.OMI_CHAT_MODEL);

  let stt: ReturnType<typeof resolveDevSttConfig>;
  try {
    stt = resolveDevSttConfig({
      OMI_STT_ENGINE: process.env.OMI_STT_ENGINE,
      OMI_STT_MODEL: process.env.OMI_STT_MODEL,
      OMI_STT_VENV: process.env.OMI_STT_VENV,
    });
  } catch (error) {
    if (error instanceof DevSttConfigError) fail(error.message, "invalid_stt");
    throw error;
  }

  return Object.freeze({
    port,
    ownerAccountId: process.env.OMI_SEED_OWNER || DEFAULT_OWNER,
    memoryCount,
    accountTimezone,
    // In-memory by default so a cold checkout needs no file, no migration step,
    // and no cleanup, and so every boot is byte-identical.
    databasePath: process.env.OMI_QA_DB || ":memory:",
    devSecretLabel: process.env.OMI_DEV_TOKEN_SECRET || DEV_KEY_MATERIAL_LABEL,
    runId: rawRunId ?? null,
    readyRecordPath: rawReadyRecordPath ?? null,
    seedPersona,
    llmGateway,
    generationLiveness,
    stt,
  });
};

const openDatabase = (path: string): Database => {
  if (path === ":memory:") return new Database(":memory:");
  try {
    return new Database(path, { create: true });
  } catch {
    return fail(
      `cannot open the QA database at "${path}". `
      + `Check the directory exists and is writable, or unset OMI_QA_DB to use `
      + `an in-memory database (the default, and what a cold checkout should use).`,
      "database_unopenable",
    );
  }
};

const main = async (): Promise<void> => {
  const config = readConfig();
  const db = openDatabase(config.databasePath);
  const stores = createSqliteLocalServiceStores(db);

  const engineIdentity = config.llmGateway === null
    ? null
    : await probeGatewayEngineIdentity(config.llmGateway.url);
  let serviceForGatewayTools: ReturnType<typeof createLocalDevService> | null = null;
  const generationSource = config.llmGateway === null
    ? createGatewayRequiredChatGenerationSource()
    : createGatewayChatGenerationSource({
      gatewayUrl: config.llmGateway.url,
      laneId: config.llmGateway.laneId,
      serviceToken: config.llmGateway.token,
      ...(engineIdentity === null ? {} : { engineIdentity }),
      // Gateway tools are composed only for an explicitly configured gateway.
      // The closure binds the already-built authenticated app, so the tool
      // cannot bypass the canonical `/v1/tasks` authorization/read path.
      readOnlyToolLoopForInput: (input) => {
        const service = serviceForGatewayTools;
        if (service === null) return undefined;
        const ownerAccountId = service.seedIdentity().owner_account_id;
        if (typeof ownerAccountId !== "string" || ownerAccountId !== input.context.ownerAccountId) {
          throw new Error("gateway tool owner mismatch");
        }
        return createProductionGatewayToolLoop({
          fetch: (request) => service.app.fetch(request),
          bearerToken: service.devToken,
          nowEpochMilliseconds: () => Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC),
          agentRunEvents: service.writePath.agentRunEvents,
          approvalCoordinator: service.writePath.agentApprovalCoordinator,
        });
      },
    });
  let service: ReturnType<typeof createLocalDevService>;
  const transcriptionSource = config.stt.kind === "mlx-whisper"
    ? createMlxWhisperTranscriptionSource({
      subprocess: {
        pythonPath: config.stt.pythonPath,
        workerPath: config.stt.workerPath,
        model: config.stt.model,
        hfHome: config.stt.hfHome,
      },
    })
    : null;
  try {
    service = createLocalDevService({
      db,
      stores,
      persistentQaStores: true,
      ownerAccountId: config.ownerAccountId,
      memoryCount: config.memoryCount,
      accountTimezone: config.accountTimezone,
      devSecretLabel: config.devSecretLabel,
      listenDefaultUnmetered: true,
      generationSource,
      ...(transcriptionSource === null ? {} : { transcriptionSource }),
      screenRetentionIntervalMs: SCREEN_RETENTION_INTERVAL_MS,
      ...(config.generationLiveness === null
        ? {}
        : { generationLiveness: config.generationLiveness }),
      ...(config.seedPersona === "demo"
        ? { seedPersona: "demo" as const, overlaySeed: applyDemoPersonaSeed }
        : {}),
    });
    serviceForGatewayTools = service;
  } catch (error) {
    void transcriptionSource?.dispose();
    return fail(`failed to seed QA data: ${error instanceof Error ? error.message : "unknown error"}`, "seed_failed");
  }

  let server: { stop: (closeActive?: boolean) => void };
  try {
    server = Bun.serve({
      // Loopback ONLY. Omitting hostname makes Bun bind 0.0.0.0, which publishes
      // this service to the LAN. That exact bug shipped silently in an earlier
      // wave and a loopback curl did not catch it, because a loopback curl
      // succeeds either way.
      hostname: LOOPBACK_HOST,
      port: config.port,
      fetch: service.app.fetch,
      websocket: service.websocket,
    });
  } catch (error) {
    void transcriptionSource?.dispose();
    const message = error instanceof Error ? error.message : "";
    if (/EADDRINUSE|address already in use/i.test(message)) {
      return fail(
        `port ${config.port} is already in use. Something else is listening.\n`
        + `  Find it:  lsof -nP -iTCP:${config.port} -sTCP:LISTEN\n`
        + `  Stop the existing listener before booting the one service door.`,
        "bind_in_use",
      );
    }
    return fail(`failed to bind ${LOOPBACK_HOST}:${config.port}.`, "bind_failed");
  }

  const baseUrl = `http://${LOOPBACK_HOST}:${config.port}`;
  if (config.readyRecordPath !== null && config.runId !== null) {
    try {
      writeFileSync(config.readyRecordPath, `${JSON.stringify({
        schema: "omi.dev-service-readiness.v1",
        runId: config.runId,
        executable: "apps/service/bin/dev-server.ts",
        baseUrl,
        databasePath: config.databasePath,
        pid: process.pid,
        evidencePath: QA_EVIDENCE_PATH,
        devToken: service.devToken,
        ownerAccountId: config.ownerAccountId,
      })}\n`, { encoding: "utf8", mode: 0o600 });
    } catch {
      server.stop(true);
      void transcriptionSource?.dispose();
      db.close();
      return fail("could not write the host-owned readiness record.", "readiness_write_failed");
    }
  }
  process.stdout.write(
    `\nomi local backend is up\n\n`
    + `  base URL      ${baseUrl}\n`
    + `  bound to      ${LOOPBACK_HOST} (loopback only - not reachable from the LAN)\n`
    + `  seed identity ${config.ownerAccountId}, ${config.memoryCount} memories, ${config.accountTimezone}`
    + `${config.seedPersona === "demo" ? ", persona demo (Demo User)" : ""}\n`
    + `  time anchor   ${QA_FIXTURE_TIME_ANCHOR_UTC}\n`
    + `  storage       ${config.databasePath} (SQLite, QA fixture only - never production authority)\n`
    + `  stt           ${config.stt.kind === "mlx-whisper"
      ? "mlx-whisper (on-device, chunked windows; dev-grade)"
      : "scripted (unset OMI_STT_ENGINE)"}\n\n`
    + `  dev token\n    ${service.devToken}\n\n`
    + `  try it\n`
    + `    TOKEN='${service.devToken}'\n`
    + `    curl -s -H "Authorization: Bearer $TOKEN" "${baseUrl}/v1/memories?limit=5"\n`
    + `    curl -s ${baseUrl}/v1/qa/status\n`
    + `    curl -s -X POST -H "Authorization: Bearer $TOKEN" ${baseUrl}/v1/qa/reset\n\n`
    + `  served-request count prints below whenever it changes.\n`
    + `  if it stays at 0 while the app shows memories, the app is NOT talking to this backend.\n\n`,
  );
  const gatewayModel = bootGatewayModel(engineIdentity);
  appendRuntimeLog({
    proc: "service",
    level: "info",
    event: "service.boot",
    persona: config.seedPersona === "demo" ? "demo" : "qa",
    stt_engine: config.stt.kind,
    gateway_kind: bootGatewayKind(engineIdentity),
    ...(gatewayModel === null ? {} : { gateway_model: gatewayModel }),
    port: config.port,
    storage: config.databasePath === ":memory:" ? ":memory:" : "file",
  });
  appendRuntimeLog({
    proc: "service",
    level: "info",
    event: "service.ready",
    port: config.port,
  });

  // Runtime served-count visibility for a human watching the demo. This is the
  // wave-9 detector: a bridge that reported itself active while serving zero
  // domain requests looked exactly like a healthy one.
  let lastReported = -1;
  const heartbeat = setInterval(() => {
    const snapshot = service.counter.snapshot();
    if (snapshot.domainReadsServed === lastReported) return;
    lastReported = snapshot.domainReadsServed;
    process.stdout.write(
      `[served] domain-reads=${snapshot.domainReadsServed}`
      + ` denied=${snapshot.domainReadsDenied}`
      + ` failed=${snapshot.domainReadsFailed}`
      + ` other=${snapshot.nonDomainRequests}\n`,
    );
  }, 1_000);

  const shutdown = (): void => {
    clearInterval(heartbeat);
    appendRuntimeLog({ proc: "service", level: "info", event: "service.shutdown" });
    server.stop(true);
    void transcriptionSource?.dispose();
    db.close();
    process.stdout.write("\nomi dev-server: stopped\n");
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
};

void main();
