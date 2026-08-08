import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { QA_API_SERVER_ENTRY, LOOPBACK_HOST, QA_BEARER_TOKEN, STOP_GRACE_MS } from './constants.mjs';

/**
 * Reserve an ephemeral loopback port by binding 0 and releasing the listener.
 * @returns {Promise<number>}
 */
export function allocateEphemeralPort(host = LOOPBACK_HOST) {
  return new Promise((resolve, reject) => {
    const listener = createServer();
    listener.once('error', reject);
    listener.listen(0, host, () => {
      const address = listener.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      listener.close((err) => (err ? reject(err) : resolve(port)));
    });
  });
}

/**
 * @param {string} baseUrl
 * @param {string} token
 * @param {{ maxAttempts?: number, intervalMs?: number }} [options]
 */
export async function waitForReadiness(baseUrl, token, options = {}) {
  const { maxAttempts = 100, intervalMs = 25 } = options;
  const headers = { authorization: `Bearer ${token}` };
  let lastError;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/__qa/status`, { headers });
      if (!response.ok) {
        lastError = new Error(`readiness probe HTTP ${response.status}`);
      } else {
        const body = await response.json();
        if (typeof body?.hitCount === 'number' && body?.counts && typeof body.counts === 'object') {
          return { baseUrl, status: body };
        }
        lastError = new Error('readiness probe returned unexpected shape');
      }
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(
    `qa-api-server not ready at ${baseUrl} after ${maxAttempts} route polls: ${lastError?.message ?? 'unknown'}`,
  );
}

/**
 * Start the external qa-api-server child on a loopback port.
 *
 * @param {{ port?: number, host?: string, serverEntry?: string, token?: string }} [options]
 * @returns {Promise<{ host: string, port: number, baseUrl: string, stop: () => Promise<void> }>}
 */
export async function bootLegacyServer(options = {}) {
  const host = options.host ?? LOOPBACK_HOST;
  const token = options.token ?? QA_BEARER_TOKEN;
  const serverEntry = options.serverEntry ?? QA_API_SERVER_ENTRY;
  const port =
    options.port === undefined ? await allocateEphemeralPort(host) : options.port;

  const child = spawn(process.execPath, [serverEntry], {
    env: { ...process.env, QA_API_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let stopped = false;
  let stopPromise;

  const stop = () => {
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {
      if (stopped) return;
      stopped = true;
      if (child.exitCode !== null || child.signalCode !== null) return;

      const exited = new Promise((resolve) => {
        child.once('exit', resolve);
      });

      child.kill('SIGTERM');

      const killer = setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) {
          child.kill('SIGKILL');
        }
      }, STOP_GRACE_MS);
      killer.unref?.();

      await exited;
      clearTimeout(killer);
    })();
    return stopPromise;
  };

  child.once('exit', (code, signal) => {
    if (!stopped && code !== 0 && code !== null) {
      stopped = true;
    }
    void signal;
  });

  const stderrChunks = [];
  child.stderr?.on('data', (chunk) => {
    stderrChunks.push(chunk);
  });

  const baseUrl = `http://${host}:${port}`;

  try {
    await waitForReadiness(baseUrl, token);
  } catch (err) {
    await stop();
    const detail = Buffer.concat(stderrChunks).toString('utf8').trim();
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(detail ? `${msg}\nserver stderr: ${detail}` : msg);
  }

  if (child.exitCode !== null) {
    const detail = Buffer.concat(stderrChunks).toString('utf8').trim();
    throw new Error(
      detail
        ? `qa-api-server exited before readiness (${child.exitCode}): ${detail}`
        : `qa-api-server exited before readiness (${child.exitCode})`,
    );
  }

  return { host, port, baseUrl, stop };
}
