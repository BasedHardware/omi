import { describe, it, after } from 'node:test';
import assert from 'node:assert/strict';
import { bootLegacyServer, waitForReadiness } from './boot.mjs';
import { QA_BEARER_TOKEN } from './constants.mjs';

describe('bootLegacyServer', () => {
  /** @type {Array<() => Promise<void>>} */
  const cleanups = [];

  after(async () => {
    await Promise.all(cleanups.map((stop) => stop()));
  });

  // red-proof: return a fixed port (4747) instead of allocateEphemeralPort() when port is omitted
  it('binds an ephemeral loopback port and becomes ready via /__qa/status', async () => {
    const server = await bootLegacyServer();
    cleanups.push(server.stop);

    assert.equal(server.host, '127.0.0.1');
    assert.ok(server.port > 0);
    assert.notEqual(server.port, 4747, 'default boot must not reuse the fake server fixed default');

    const status = await waitForReadiness(server.baseUrl, QA_BEARER_TOKEN, {
      maxAttempts: 1,
      intervalMs: 0,
    });
    assert.equal(typeof status.status.hitCount, 'number');
    assert.ok(status.status.counts.tasks >= 1);
    assert.match(server.baseUrl, /^http:\/\/127\.0\.0\.1:\d+$/);
  });

  // red-proof: make stop() a no-op so the child survives after the test body
  it('stop() is idempotent and reaps the child process', async () => {
    const server = await bootLegacyServer();
    const { port } = server;

    await server.stop();
    await server.stop();

    let connectionRefused = false;
    try {
      await fetch(`http://127.0.0.1:${port}/__qa/status`, {
        headers: { authorization: `Bearer ${QA_BEARER_TOKEN}` },
      });
    } catch (err) {
      connectionRefused = err instanceof TypeError || (err instanceof Error && /fetch/i.test(err.message));
    }
    assert.ok(connectionRefused, 'server port must be closed after stop()');
  });
});
