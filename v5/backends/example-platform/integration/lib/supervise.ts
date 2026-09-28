/**
 * Child-process supervision for overnight end-to-end harnesses.
 *
 * HARD INVARIANT (earned by incident): child process EXIT is part of
 * acceptance. HTTP readiness alone is insufficient — a child can become
 * ready and then fail its own acceptance probe / exit nonzero. Callers must
 * await the exact child's exit and propagate that status.
 */

import type { Subprocess } from "bun";

const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_KILL_GRACE_MS = 2_000;
const DEFAULT_READY_POLL_MS = 50;

export type SuperviseChildOptions = {
  command: string[];
  cwd?: string;
  env?: Record<string, string | undefined>;
  /** Overall wall-clock bound for the child's lifetime. Default 60s. */
  timeoutMs?: number;
  /** Grace between SIGTERM and SIGKILL on timeout/stop. Default 2s. */
  killGraceMs?: number;
};

export type SuperviseChildResult = {
  exitCode: number | null;
  signal: string | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  durationMs: number;
};

export type ExitStatus = {
  exitCode: number | null;
  signal: string | null;
};

export type WaitForHttpReadyOptions = {
  timeoutMs?: number;
  pollIntervalMs?: number;
};

export type ManagedProcessOptions = {
  command: string[];
  /** URL polled by {@link ManagedProcess.ready}. Not a substitute for exit. */
  readyUrl: string;
  cwd?: string;
  env?: Record<string, string | undefined>;
  readyTimeoutMs?: number;
  killGraceMs?: number;
  readyPollIntervalMs?: number;
};

// --- orphan prevention -------------------------------------------------------

const liveChildren = new Set<Subprocess>();
let cleanupHooksInstalled = false;

function installCleanupHooks(): void {
  if (cleanupHooksInstalled) return;
  cleanupHooksInstalled = true;

  const reap = (): void => {
    for (const child of liveChildren) {
      try {
        child.kill("SIGKILL");
      } catch {
        // already dead
      }
    }
    liveChildren.clear();
  };

  process.on("exit", reap);
  process.on("SIGINT", () => {
    reap();
    process.exit(130);
  });
  process.on("SIGTERM", () => {
    reap();
    process.exit(143);
  });
}

function track(child: Subprocess): void {
  installCleanupHooks();
  liveChildren.add(child);
}

function untrack(child: Subprocess): void {
  liveChildren.delete(child);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * SIGTERM, then SIGKILL after grace if the child is still alive.
 * Always eventually awaits process death when possible.
 */
export async function escalateKill(
  child: Subprocess,
  killGraceMs: number = DEFAULT_KILL_GRACE_MS,
): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  try {
    child.kill("SIGTERM");
  } catch {
    return;
  }
  const graceDeadline = Date.now() + killGraceMs;
  while (Date.now() < graceDeadline) {
    if (child.exitCode !== null || child.signalCode !== null) return;
    await sleep(25);
  }
  if (child.exitCode === null && child.signalCode === null) {
    try {
      child.kill("SIGKILL");
    } catch {
      // already dead
    }
  }
}

/**
 * Poll until `url` produces an HTTP response (any status).
 *
 * NOT A SUBSTITUTE FOR EXIT STATUS. Readiness only means the server accepted
 * a connection — it does not mean the child's acceptance probes passed, and
 * it does not mean the child exited 0. Always await the exact child process
 * exit (via {@link superviseChild} or {@link ManagedProcess.exited}) and
 * treat a nonzero exit as harness failure even when this function succeeded.
 */
export async function waitForHttpReady(
  url: string,
  opts: WaitForHttpReadyOptions = {},
): Promise<void> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const pollIntervalMs = opts.pollIntervalMs ?? DEFAULT_READY_POLL_MS;
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;

  while (Date.now() < deadline) {
    try {
      const remaining = Math.max(1, deadline - Date.now());
      const response = await fetch(url, {
        signal: AbortSignal.timeout(Math.min(1_000, remaining)),
      });
      // Any HTTP response means the listener is up.
      void response.status;
      return;
    } catch (err) {
      lastError = err;
    }
    await sleep(pollIntervalMs);
  }

  const detail =
    lastError instanceof Error ? lastError.message : String(lastError ?? "unknown");
  throw new Error(
    `waitForHttpReady timed out after ${timeoutMs}ms for ${url} (last error: ${detail})`,
  );
}

/**
 * Spawn a child, await its exit (bounded), capture stdio, propagate status.
 *
 * This is the acceptance path for one-shot children: the returned `exitCode` /
 * `signal` ARE the acceptance signal. Do not wrap this by only checking HTTP.
 */
export async function superviseChild(
  options: SuperviseChildOptions,
): Promise<SuperviseChildResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const killGraceMs = options.killGraceMs ?? DEFAULT_KILL_GRACE_MS;
  const startedAt = Date.now();

  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) env[key] = value;
  }
  if (options.env) {
    for (const [key, value] of Object.entries(options.env)) {
      if (value === undefined) delete env[key];
      else env[key] = value;
    }
  }

  const child = Bun.spawn(options.command, {
    cwd: options.cwd,
    env,
    stdout: "pipe",
    stderr: "pipe",
    stdin: "ignore",
  });
  track(child);

  let timedOut = false;
  const timeoutHandle = setTimeout(() => {
    timedOut = true;
    void escalateKill(child, killGraceMs);
  }, timeoutMs);

  try {
    const stdoutPromise = new Response(child.stdout).text();
    const stderrPromise = new Response(child.stderr).text();
    // Await the EXACT child's exit — not a readiness proxy.
    await child.exited;
    const [stdout, stderr] = await Promise.all([stdoutPromise, stderrPromise]);

    return {
      // Use Bun's split fields: signal kills leave exitCode null + signal set.
      exitCode: child.exitCode,
      signal: child.signalCode,
      stdout,
      stderr,
      timedOut,
      durationMs: Date.now() - startedAt,
    };
  } finally {
    clearTimeout(timeoutHandle);
    untrack(child);
  }
}

/**
 * Long-lived server child. Readiness ({@link ready}) and exit ({@link exited})
 * are separate awaits — both must be surfaced to the harness. `.ready()`
 * succeeding never authorizes treating the run as passed.
 */
export class ManagedProcess {
  readonly exited: Promise<ExitStatus>;
  private readonly child: Subprocess;
  private readonly readyUrl: string;
  private readonly readyTimeoutMs: number;
  private readonly readyPollIntervalMs: number;
  private readonly killGraceMs: number;
  private stopPromise: Promise<void> | null = null;
  private readonly stdoutPromise: Promise<string>;
  private readonly stderrPromise: Promise<string>;

  private constructor(
    child: Subprocess,
    options: Required<
      Pick<
        ManagedProcessOptions,
        "readyUrl" | "readyTimeoutMs" | "killGraceMs" | "readyPollIntervalMs"
      >
    >,
  ) {
    this.child = child;
    this.readyUrl = options.readyUrl;
    this.readyTimeoutMs = options.readyTimeoutMs;
    this.readyPollIntervalMs = options.readyPollIntervalMs;
    this.killGraceMs = options.killGraceMs;
    this.stdoutPromise = new Response(child.stdout).text();
    this.stderrPromise = new Response(child.stderr).text();
    this.exited = child.exited.then(() => {
      untrack(child);
      return { exitCode: child.exitCode, signal: child.signalCode };
    });
  }

  static start(options: ManagedProcessOptions): ManagedProcess {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (value !== undefined) env[key] = value;
    }
    if (options.env) {
      for (const [key, value] of Object.entries(options.env)) {
        if (value === undefined) delete env[key];
        else env[key] = value;
      }
    }

    const child = Bun.spawn(options.command, {
      cwd: options.cwd,
      env,
      stdout: "pipe",
      stderr: "pipe",
      stdin: "ignore",
    });
    track(child);

    return new ManagedProcess(child, {
      readyUrl: options.readyUrl,
      readyTimeoutMs: options.readyTimeoutMs ?? DEFAULT_TIMEOUT_MS,
      killGraceMs: options.killGraceMs ?? DEFAULT_KILL_GRACE_MS,
      readyPollIntervalMs: options.readyPollIntervalMs ?? DEFAULT_READY_POLL_MS,
    });
  }

  get pid(): number | undefined {
    return this.child.pid;
  }

  /**
   * Await HTTP readiness only. Separately await {@link exited} for acceptance.
   */
  async ready(): Promise<void> {
    await waitForHttpReady(this.readyUrl, {
      timeoutMs: this.readyTimeoutMs,
      pollIntervalMs: this.readyPollIntervalMs,
    });
  }

  /** Idempotent stop: SIGTERM, then SIGKILL after grace, then await exit. */
  stop(): Promise<void> {
    if (this.stopPromise) return this.stopPromise;
    this.stopPromise = (async () => {
      await escalateKill(this.child, this.killGraceMs);
      await this.exited;
      // Drain pipes so the child is fully reaped.
      await Promise.all([this.stdoutPromise, this.stderrPromise]);
    })();
    return this.stopPromise;
  }
}
