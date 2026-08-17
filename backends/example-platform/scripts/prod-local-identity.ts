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
  existsSync, mkdirSync, readFileSync, rmSync, writeFileSync,
} from "node:fs";
import { dirname } from "node:path";

export const LOCAL_FIREBASE_PROJECT_ID = "omi-local-pg";
export const AUTH_EMULATOR_HOST = "127.0.0.1";
export const AUTH_EMULATOR_PORT = 19_099;
export const AUTH_EMULATOR_HUB_PORT = 14_400;
export const AUTH_EMULATOR_LOGGING_PORT = 14_500;
export const FIREBASE_AUTH_EMULATOR_HOST_VALUE = `${AUTH_EMULATOR_HOST}:${AUTH_EMULATOR_PORT}`;
export const IDENTITY_STATE_ROOT = "/Volumes/Ephemeral/scratch/omi-prod-local-identity";
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

const fail = (message: string): never => {
  process.stderr.write(`\n${message}\n\n`);
  process.exit(1);
};

const portListeners = (port: number): string => {
  const result = Bun.spawnSync(["lsof", "-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], {
    stdout: "pipe",
    stderr: "pipe",
  });
  return result.stdout.toString();
};

const portHeld = (port: number): boolean => portListeners(port).includes("(LISTEN)");

const processAlive = (pid: number): boolean => {
  const result = Bun.spawnSync(["kill", "-0", String(pid)], { stdout: "pipe", stderr: "pipe" });
  return result.exitCode === 0;
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

const ownedProcesses = (): readonly number[] => {
  const result = Bun.spawnSync(["pgrep", "-f", IDENTITY_FIREBASE_JSON], {
    stdout: "pipe",
    stderr: "pipe",
  });
  if (result.exitCode !== 0) return [];
  return result.stdout.toString().split("\n")
    .map((line) => Number(line.trim()))
    .filter((pid) => Number.isSafeInteger(pid) && pid > 1);
};

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
    const response = await fetch(`http://${FIREBASE_AUTH_EMULATOR_HOST_VALUE}/`);
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

const startOwned = async (): Promise<void> => {
  const existing = loadPidFile();
  if (existing !== null && processAlive(existing.pid) && portHeld(AUTH_EMULATOR_PORT)
    && await emulatorReady()) {
    process.stdout.write(
      `omi prod-local-identity: reusing owned Auth emulator on ${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`
      + `  export FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`,
    );
    return;
  }
  if (portHeld(AUTH_EMULATOR_PORT)) {
    return fail(
      `${PROD_LOCAL_IDENTITY_PORT_HELD}\n`
      + `  ${portListeners(AUTH_EMULATOR_PORT).trim()}\n`
      + `  Find it: lsof -nP -iTCP:${AUTH_EMULATOR_PORT} -sTCP:LISTEN`,
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
  const started = Bun.spawnSync(["sh", "-c", [
    "nohup npx --yes firebase-tools emulators:start",
    "--only auth",
    `--project ${LOCAL_FIREBASE_PROJECT_ID}`,
    `--config ${IDENTITY_FIREBASE_JSON}`,
    `>> ${IDENTITY_LOG_FILE} 2>&1 &`,
    "echo $!",
  ].join(" ")], {
    cwd: IDENTITY_STATE_ROOT,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      FIREBASE_AUTH_EMULATOR_HOST: FIREBASE_AUTH_EMULATOR_HOST_VALUE,
    },
  });
  const pid = Number(started.stdout.toString().trim().split("\n").at(-1));
  if (started.exitCode !== 0 || !Number.isSafeInteger(pid) || pid < 1) {
    return fail(
      "omi prod-local-identity: failed to spawn firebase-tools.\n"
      + `  log: ${IDENTITY_LOG_FILE}`,
    );
  }
  writeFileSync(IDENTITY_PID_FILE, `${JSON.stringify({
    version: "omi-prod-local-identity-v1",
    pid,
    authPort: AUTH_EMULATOR_PORT,
    configPath: IDENTITY_FIREBASE_JSON,
  }, null, 2)}\n`, { mode: 0o600 });

  const ready = await waitUntil(emulatorReady, READY_TIMEOUT_MS);
  if (!ready) {
    await stopOwned();
    return fail(
      "omi prod-local-identity: Auth emulator did not become ready.\n"
      + `  log: ${IDENTITY_LOG_FILE}`,
    );
  }
  process.stdout.write(
    `omi prod-local-identity: Auth emulator started on ${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`
    + `  project ${LOCAL_FIREBASE_PROJECT_ID} (auth only; ui disabled)\n`
    + `  export FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST_VALUE}\n`,
  );
};

const killPid = (pid: number): void => {
  Bun.spawnSync(["kill", "-TERM", String(pid)], { stdout: "pipe", stderr: "pipe" });
};

const stopOwned = async (): Promise<void> => {
  const recorded = loadPidFile();
  const pids = new Set<number>(ownedProcesses());
  if (recorded !== null) pids.add(recorded.pid);
  for (const pid of pids) {
    if (processAlive(pid)) killPid(pid);
  }
  const gone = await waitUntil(async () => !portHeld(AUTH_EMULATOR_PORT)
    && ownedProcesses().every((pid) => !processAlive(pid)), STOP_TIMEOUT_MS);
  if (!gone) {
    for (const pid of [...ownedProcesses(), recorded?.pid].filter((pid): pid is number => pid !== undefined)) {
      if (processAlive(pid)) {
        Bun.spawnSync(["kill", "-KILL", String(pid)], { stdout: "pipe", stderr: "pipe" });
      }
    }
    await waitUntil(async () => !portHeld(AUTH_EMULATOR_PORT), 2_000);
  }
  if (existsSync(IDENTITY_PID_FILE)) rmSync(IDENTITY_PID_FILE);
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
  await main();
}
