#!/usr/bin/env bun
/**
 * Owned Firebase Auth emulator + mint tooling for `bun run prod-local --local-identity`.
 *
 * This is a local-only artifact. The idToken printed by `--mint` is an emulator
 * JWT, worthless off this machine, and is never a production credential.
 *
 * Usage:
 *   bun run scripts/prod-local-identity.ts --start
 *   bun run scripts/prod-local-identity.ts --mint
 *   bun run scripts/prod-local-identity.ts --stop
 *   bun run scripts/prod-local-identity.ts --status
 *
 * State lives under /Volumes/Ephemeral/scratch/omi-prod-local-identity (not
 * the product worktree). `--stop` kills the owned process group; `--start`
 * reuses a live owned emulator and refuses a foreign listener on the port.
 */

import {
  existsSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync, openSync, closeSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { spawn, spawnSync } from "node:child_process";

export const LOCAL_FIREBASE_PROJECT_ID = "omi-local-pg";
export const AUTH_EMULATOR_HOST = "127.0.0.1";
export const AUTH_EMULATOR_PORT = 19_099;
export const AUTH_EMULATOR_HUB_PORT = 14_400;
export const AUTH_EMULATOR_LOGGING_PORT = 14_500;
export const FIREBASE_AUTH_EMULATOR_HOST_VALUE = `${AUTH_EMULATOR_HOST}:${AUTH_EMULATOR_PORT}`;
export const IDENTITY_STATE_ROOT = join(tmpdir(), "omi-prod-local-identity");
export const FIREBASE_TOOLS_VERSION = "15.25.1";
export const IDENTITY_PID_FILE = `${IDENTITY_STATE_ROOT}/emulator.pid`;
export const IDENTITY_LOG_FILE = `${IDENTITY_STATE_ROOT}/emulator.log`;
export const IDENTITY_FIREBASE_JSON = `${IDENTITY_STATE_ROOT}/firebase.json`;
export const IDENTITY_FIREBASERC = `${IDENTITY_STATE_ROOT}/.firebaserc`;

export const PROD_LOCAL_IDENTITY_PORT_HELD =
  "omi prod-local-identity: Auth emulator port is held by a process this script does not own.";
export const PROD_LOCAL_IDENTITY_NOT_RUNNING =
  "omi prod-local-identity: owned Auth emulator is not running.";
export const PROD_LOCAL_IDENTITY_USAGE =
  "omi prod-local-identity: usage: --start | --stop | --status | --mint";

const READY_TIMEOUT_MS = 45_000;
const STOP_TIMEOUT_MS = 10_000;

export type IdentityAction = "start" | "stop" | "status" | "mint";

export interface OwnedEmulatorPid {
  readonly version: "omi-prod-local-identity-v1";
  readonly pid: number;
  readonly authPort: number;
  readonly configPath: string;
}

export const parseIdentityAction = (argv: readonly string[]): IdentityAction | null => {
  const flags = argv.filter((entry) => entry.startsWith("--"));
  if (flags.length !== 1) return null;
  const flag = flags[0];
  if (flag === "--start") return "start";
  if (flag === "--stop") return "stop";
  if (flag === "--status") return "status";
  if (flag === "--mint") return "mint";
  return null;
};

export const firebaseEmulatorConfig = (): Readonly<{
  readonly emulators: {
    readonly auth: { readonly host: string; readonly port: number };
    readonly ui: { readonly enabled: false };
    readonly hub: { readonly host: string; readonly port: number };
    readonly logging: { readonly host: string; readonly port: number };
  };
}> => Object.freeze({
  emulators: Object.freeze({
    auth: Object.freeze({ host: AUTH_EMULATOR_HOST, port: AUTH_EMULATOR_PORT }),
    ui: Object.freeze({ enabled: false as const }),
    hub: Object.freeze({ host: AUTH_EMULATOR_HOST, port: AUTH_EMULATOR_HUB_PORT }),
    logging: Object.freeze({ host: AUTH_EMULATOR_HOST, port: AUTH_EMULATOR_LOGGING_PORT }),
  }),
});

export const withIdentityLease = async <Result>(
  callback: (token: string) => Promise<Result>, inheritedToken?: string, stateRoot = IDENTITY_STATE_ROOT,
): Promise<Result> => {
  mkdirSync(stateRoot, { recursive: true, mode: 0o700 });
  const leasePath = join(stateRoot, "lifecycle.lease");
  if (inheritedToken !== undefined) {
    if (!/^[a-f0-9-]{36}$/.test(inheritedToken) || !existsSync(leasePath)
      || readFileSync(leasePath, "utf8") !== inheritedToken)
      throw new Error("omi prod-local-identity: invalid inherited lifecycle lease.");
    return callback(inheritedToken);
  }
  const token = crypto.randomUUID();
  const descriptor = openSync(leasePath, "wx", 0o600);
  try {
    writeFileSync(descriptor, token);
    return await callback(token);
  } finally { closeSync(descriptor); rmSync(leasePath, { force: true }); }
};

const fail = (message: string): never => { throw new Error(message); };

export const portHeld = (port: number): boolean => {
  try {
    const probe = Bun.serve({ hostname: AUTH_EMULATOR_HOST, port, fetch: () => new Response(null, { status: 503 }) });
    probe.stop(true);
    return false;
  } catch (cause) {
    if ((cause as { code?: string }).code === "EADDRINUSE") return true;
    throw cause;
  }
};

const processAlive = (pid: number): boolean => {
  try { process.kill(pid, 0); return true; } catch { return false; }
};

export const ownedPidMatches = (record: OwnedEmulatorPid, command: string): boolean =>
  command.includes(IDENTITY_FIREBASE_JSON) && command.includes("emulators:start")
    && command.includes("firebase") && record.configPath === IDENTITY_FIREBASE_JSON
    && record.authPort === AUTH_EMULATOR_PORT;

const verifiedOwnedPid = (record: OwnedEmulatorPid): boolean => {
  const result = spawnSync("ps", ["-p", String(record.pid), "-o", "pgid=", "-o", "command="], { encoding: "utf8", timeout: 2000 });
  if (result.error) throw new Error("omi prod-local-identity: cannot verify process ownership.");
  const row = /^\s*(\d+)\s+(.+)$/s.exec(result.stdout.trim());
  return result.status === 0 && row !== null && Number(row[1]) === record.pid && ownedPidMatches(record, row[2]!);
};

export const signalOwnedEmulator = (record: OwnedEmulatorPid, signal: "SIGTERM" | "SIGKILL"): void => {
  if (!verifiedOwnedPid(record)) throw new Error("omi prod-local-identity: recorded PID is not the owned emulator; refusing to signal it.");
  process.kill(-record.pid, signal);
};

export const installedFirebaseCli = (): string => {
  const binary = Bun.which("firebase");
  if (!binary) throw new Error("omi prod-local-identity: install firebase-tools 15.25.1 before running.");
  const path = realpathSync(binary);
  const manifest = JSON.parse(readFileSync(join(dirname(path), "../../package.json"), "utf8"));
  if (manifest.name !== "firebase-tools" || manifest.version !== FIREBASE_TOOLS_VERSION)
    throw new Error("omi prod-local-identity: installed firebase-tools version must be 15.25.1.");
  return path;
};

const parsePidFile = (raw: string): OwnedEmulatorPid | null => {
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (value["version"] !== "omi-prod-local-identity-v1"
      || typeof value["pid"] !== "number" || !Number.isSafeInteger(value["pid"]) || value["pid"] < 1
      || value["authPort"] !== AUTH_EMULATOR_PORT
      || value["configPath"] !== IDENTITY_FIREBASE_JSON) return null;
    return Object.freeze({
      version: "omi-prod-local-identity-v1",
      pid: value["pid"],
      authPort: AUTH_EMULATOR_PORT,
      configPath: IDENTITY_FIREBASE_JSON,
    });
  } catch {
    return null;
  }
};

const loadPidFile = (): OwnedEmulatorPid | null => {
  if (!existsSync(IDENTITY_PID_FILE)) return null;
  return parsePidFile(readFileSync(IDENTITY_PID_FILE, "utf8"));
};

export const emulatorChildEnvironment = (env: NodeJS.ProcessEnv, executable = process.execPath): NodeJS.ProcessEnv => ({
  ...env, PATH: dirname(executable), FIREBASE_AUTH_EMULATOR_HOST: FIREBASE_AUTH_EMULATOR_HOST_VALUE,
});

const writeOwnedConfig = (): void => {
  mkdirSync(IDENTITY_STATE_ROOT, { recursive: true, mode: 0o700 });
  writeFileSync(IDENTITY_FIREBASE_JSON, `${JSON.stringify(firebaseEmulatorConfig(), null, 2)}\n`, {
    mode: 0o600,
  });
  writeFileSync(
    IDENTITY_FIREBASERC,
    `${JSON.stringify({ projects: { default: LOCAL_FIREBASE_PROJECT_ID } }, null, 2)}\n`,
    { mode: 0o600 },
  );
};

const emulatorReady = async (): Promise<boolean> => {
  try {
    const response = await fetch(`http://${FIREBASE_AUTH_EMULATOR_HOST_VALUE}/`, { signal: AbortSignal.timeout(2000) });
    return response.status >= 200 && response.status < 500;
  } catch {
    return false;
  }
};

const waitUntil = async (probe: () => Promise<boolean>, timeoutMs: number): Promise<boolean> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probe()) return true;
    await Bun.sleep(200);
  }
  return probe();
};

export const assertIdentityRuntime = (version = Bun.version): void => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  if (manifest.packageManager !== `bun@${version}`)
    throw new Error(`omi prod-local-identity: emulator startup requires the project-pinned ${manifest.packageManager}; received bun@${version}. Run this command with the pinned Bun binary.`);
};

const startOwned = async (): Promise<void> => {
  assertIdentityRuntime();
  const existing = loadPidFile();
  if (existing !== null && processAlive(existing.pid) && !verifiedOwnedPid(existing))
    throw new Error("omi prod-local-identity: existing PID is not owned.");
  if (existing !== null && verifiedOwnedPid(existing) && processAlive(existing.pid) && portHeld(AUTH_EMULATOR_PORT)
    && await emulatorReady()) {
    process.stdout.write(
      `omi prod-local-identity: reusing owned Auth emulator on ${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`
      + `  export FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`,
    );
    return;
  }
  if (existing !== null && processAlive(existing.pid))
    throw new Error("omi prod-local-identity: owned emulator is still starting or unhealthy.");
  if (portHeld(AUTH_EMULATOR_PORT)) {
    return fail(
      `${PROD_LOCAL_IDENTITY_PORT_HELD}\n`
      + `  Port ${AUTH_EMULATOR_PORT} is unavailable.`,
    );
  }
  if (portHeld(AUTH_EMULATOR_HUB_PORT) || portHeld(AUTH_EMULATOR_LOGGING_PORT)) {
    return fail(
      `${PROD_LOCAL_IDENTITY_PORT_HELD}\n`
      + `  hub ${AUTH_EMULATOR_HUB_PORT} or logging ${AUTH_EMULATOR_LOGGING_PORT} is already listening.`,
    );
  }

  writeOwnedConfig();
  mkdirSync(dirname(IDENTITY_LOG_FILE), { recursive: true, mode: 0o700 });
  const log = openSync(IDENTITY_LOG_FILE, "a", 0o600);
  let started: ReturnType<typeof spawn> | undefined;
  let record: OwnedEmulatorPid | undefined;
  try {
    started = spawn(process.execPath, [installedFirebaseCli(), "emulators:start", "--only", "auth",
      "--project", LOCAL_FIREBASE_PROJECT_ID, "--config", IDENTITY_FIREBASE_JSON], {
      cwd: IDENTITY_STATE_ROOT, detached: true, stdio: ["ignore", log, log],
      env: emulatorChildEnvironment(process.env),
    });
    await new Promise<void>((resolve, reject) => { started!.once("spawn", resolve); started!.once("error", reject); });
    record = { version: "omi-prod-local-identity-v1", pid: started.pid!,
      authPort: AUTH_EMULATOR_PORT, configPath: IDENTITY_FIREBASE_JSON };
    writeFileSync(IDENTITY_PID_FILE, `${JSON.stringify(record)}\n`, { mode: 0o600 });
    const ready = await waitUntil(emulatorReady, READY_TIMEOUT_MS);
    if (!ready) throw new Error("omi prod-local-identity: Auth emulator did not become ready.");
    started.unref();
  } catch (cause) {
    if (started?.pid && started.exitCode === null && started.signalCode === null) {
      process.kill(-started.pid, "SIGTERM");
      if (!await waitUntil(async () => started!.exitCode !== null || started!.signalCode !== null, STOP_TIMEOUT_MS)) {
        if (record !== undefined) signalOwnedEmulator(record, "SIGKILL");
        await waitUntil(async () => started!.exitCode !== null || started!.signalCode !== null, 2000);
      }
    }
    if (record !== undefined && existsSync(IDENTITY_PID_FILE) && loadPidFile()?.pid === record.pid)
      rmSync(IDENTITY_PID_FILE);
    throw cause;
  } finally { closeSync(log); }
  process.stdout.write(
    `omi prod-local-identity: Auth emulator started on ${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`
    + `  project ${LOCAL_FIREBASE_PROJECT_ID} (auth only; ui disabled)\n`
    + `  export FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`,
  );
};

export const stopOwned = async (): Promise<void> => {
  const recorded = loadPidFile();
  if (recorded === null) {
    if (portHeld(AUTH_EMULATOR_PORT)) throw new Error(PROD_LOCAL_IDENTITY_PORT_HELD);
    return;
  }
  if (processAlive(recorded.pid)) {
    signalOwnedEmulator(recorded, "SIGTERM");
    const gone = await waitUntil(async () => !processAlive(recorded.pid), STOP_TIMEOUT_MS);
    if (!gone) {
      signalOwnedEmulator(recorded, "SIGKILL");
      await waitUntil(async () => !processAlive(recorded.pid), 2000);
    }
  }
  if (portHeld(AUTH_EMULATOR_PORT) || processAlive(recorded.pid))
    throw new Error("omi prod-local-identity: emulator teardown incomplete.");
  rmSync(IDENTITY_PID_FILE, { force: true });
  process.stdout.write("omi prod-local-identity: stopped owned Auth emulator.\n");
};

const statusOwned = async (): Promise<void> => {
  const recorded = loadPidFile();
  const ready = await emulatorReady();
  process.stdout.write(`${JSON.stringify({
    configured: recorded !== null,
    pid: recorded?.pid ?? null,
    alive: recorded !== null && processAlive(recorded.pid),
    port: AUTH_EMULATOR_PORT,
    listening: portHeld(AUTH_EMULATOR_PORT),
    ready,
    host: FIREBASE_AUTH_EMULATOR_HOST_VALUE,
  })}\n`);
};

export interface MintedEmulatorIdentity {
  readonly uid: string;
  readonly idToken: string;
  readonly email: string;
}

export const mintEmulatorIdentity = async (
  emulatorHost = FIREBASE_AUTH_EMULATOR_HOST_VALUE,
): Promise<MintedEmulatorIdentity> => {
  const email = `prod-local-${crypto.randomUUID()}@omi.local`;
  const password = `local-${crypto.randomUUID()}`;
  const response = await fetch(
    `http://${emulatorHost}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-api-key`,
    {
      method: "POST",
      signal: AbortSignal.timeout(5000),
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
    },
  );
  if (!response.ok) {
    throw new Error("omi prod-local-identity: emulator signUp failed.");
  }
  const body = await response.json() as Record<string, unknown>;
  const uid = body["localId"];
  const idToken = body["idToken"];
  if (typeof uid !== "string" || uid.length < 1 || typeof idToken !== "string" || idToken.length < 1) {
    throw new Error("omi prod-local-identity: emulator signUp returned no identity.");
  }
  return Object.freeze({ uid, idToken, email });
};

const mint = async (): Promise<void> => {
  if (!await emulatorReady()) {
    return fail(
      `${PROD_LOCAL_IDENTITY_NOT_RUNNING}\n`
      + "  bun run scripts/prod-local-identity.ts --start",
    );
  }
  let minted: MintedEmulatorIdentity;
  try {
    minted = await mintEmulatorIdentity();
  } catch (error) {
    return fail(error instanceof Error ? error.message : "omi prod-local-identity: mint failed.");
  }
  process.stdout.write(
    `omi prod-local-identity: minted emulator user\n`
    + `  project ${LOCAL_FIREBASE_PROJECT_ID}\n`
    + `  uid     ${minted.uid}\n`
    + `  email   ${minted.email}\n\n`
    + "  # Emulator artifact only; worthless off this machine. Not a production credential.\n"
    + `  export FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`
    + `  export PROD_LOCAL_FIREBASE_UID=${minted.uid}\n`
    + `  Authorization: Bearer ${minted.idToken}\n`,
  );
};

const main = async (): Promise<void> => {
  const action = parseIdentityAction(process.argv.slice(2));
  if (action === null) return fail(PROD_LOCAL_IDENTITY_USAGE);
  if (action === "start") return startOwned();
  if (action === "stop") return stopOwned();
  if (action === "status") return statusOwned();
  return mint();
};

if (import.meta.main) {
  try { await withIdentityLease(async () => main(), process.env.OMI_IDENTITY_LIFECYCLE_LEASE); } catch (cause) {
    process.stderr.write(`${cause instanceof Error ? cause.message : "identity operation failed"}\n`);
    process.exitCode = 1;
  }
}
