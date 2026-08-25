import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  PersonaAuthenticationError,
  assertPersonaUidMatch,
  resolvePersonaIdentity,
  resolvePersonaOwnerIdentity,
} from './persona-chat-gateway.mjs';

test('assertPersonaUidMatch returns uid when identity matches request', () => {
  assert.equal(assertPersonaUidMatch({ uid: 'user-1' }, 'user-1'), 'user-1');
});

test('assertPersonaUidMatch rejects null/anonymous identity', () => {
  assert.throws(() => assertPersonaUidMatch(null, 'user-1'), PersonaAuthenticationError);
});

test('assertPersonaUidMatch rejects uid mismatch', () => {
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, 'attacker'),
    PersonaAuthenticationError,
  );
});

test('assertPersonaUidMatch rejects missing requested uid', () => {
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, ''),
    PersonaAuthenticationError,
  );
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, undefined),
    PersonaAuthenticationError,
  );
});

test('persona ownership keeps verified anonymous UIDs (chat tier does not)', async () => {
  const options = {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({ users: [{ localId: 'anonymous-uid', providerUserInfo: [] }] }),
  };

  // The persona creation flow signs visitors in anonymously and writes the
  // persona under that UID; 401ing it drops their plugins and facts silently.
  const owner = await resolvePersonaOwnerIdentity('Bearer anonymous-token', options);
  assert.deepEqual(owner, { uid: 'anonymous-uid' });
  assert.equal(assertPersonaUidMatch(owner, 'anonymous-uid'), 'anonymous-uid');

  // The chat tier still collapses anonymous users to the free lane.
  assert.equal(await resolvePersonaIdentity('Bearer anonymous-token', options), null);
});

test('persona ownership still rejects another user uid', async () => {
  const owner = await resolvePersonaOwnerIdentity('Bearer anonymous-token', {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({ users: [{ localId: 'anonymous-uid', providerUserInfo: [] }] }),
  });
  assert.throws(
    () => assertPersonaUidMatch(owner, 'someone-else'),
    PersonaAuthenticationError,
  );
});

test('persona ownership fails closed without a token', async () => {
  assert.equal(await resolvePersonaOwnerIdentity(null), null);
  await assert.rejects(
    resolvePersonaOwnerIdentity('Bearer bad-token', {
      firebaseApiKey: 'firebase-public-key',
      fetchImpl: async () => new Response('{}', { status: 401 }),
    }),
    PersonaAuthenticationError,
  );
});

test('persona ownership rejects a disabled account', async () => {
  await assert.rejects(
    resolvePersonaOwnerIdentity('Bearer disabled-token', {
      firebaseApiKey: 'firebase-public-key',
      fetchImpl: async () =>
        Response.json({ users: [{ localId: 'uid', disabled: true }] }),
    }),
    PersonaAuthenticationError,
  );
});

// ---------------------------------------------------------------------------
// Route-handler regression: drive the real POST handlers of both protected
// routes so removing the authorization lookup or the UID-match call from
// either production handler fails this suite, not just a unit test of the
// gateway helpers.
// ---------------------------------------------------------------------------

const require = createRequire(import.meta.url);
const ts = require('typescript');

const TEST_DIR_URL = new URL('.', import.meta.url);
const GATEWAY_SPECIFIER = '@/lib/server/persona-chat-gateway.mjs';
const GATEWAY_URL = pathToFileURL(
  path.join(fileURLToPath(TEST_DIR_URL), 'persona-chat-gateway.mjs'),
).href;

const STUB_NEXT_SERVER = `export const NextResponse = {
  json: (body, init) =>
    new Response(JSON.stringify(body ?? null), {
      status: init?.status ?? 200,
      headers: { 'content-type': 'application/json' },
    }),
};`;

const STUB_REDIS = `const state = { saddCalls: [] };
class FakeRedis {
  async sadd(key, ...members) {
    state.saddCalls.push({ key, members });
    return members.length;
  }
  on() {}
}
export const __redisState = state;
export default FakeRedis;`;

function dataUrl(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
}

const STUB_NEXT_SERVER_URL = dataUrl(STUB_NEXT_SERVER);
const STUB_REDIS_URL = dataUrl(STUB_REDIS);

let routeInstance = 0;

async function loadRouteHandler(routePath) {
  const source = await fs.readFile(new URL(routePath, TEST_DIR_URL), 'utf8');
  // Rewrite every bare specifier to something plain Node can resolve from a
  // temp file outside the package: Next's server helper and ioredis become
  // stubs, the gateway keeps its real implementation via an absolute URL.
  const rewritten = source
    .replaceAll("'next/server'", JSON.stringify(STUB_NEXT_SERVER_URL))
    .replaceAll("'ioredis'", JSON.stringify(STUB_REDIS_URL))
    .replaceAll(`'${GATEWAY_SPECIFIER}'`, JSON.stringify(GATEWAY_URL));
  const { outputText } = ts.transpileModule(rewritten, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const tmpPath = path.join(
    os.tmpdir(),
    `persona-route-under-test-${routeInstance++}.mjs`,
  );
  await fs.writeFile(tmpPath, outputText);
  try {
    return await import(pathToFileURL(tmpPath).href);
  } finally {
    await fs.rm(tmpPath, { force: true });
  }
}

async function loadRedisStub() {
  return import(STUB_REDIS_URL);
}

/**
 * Install one fetch stub covering both outbound calls the handlers make:
 * the Firebase identity lookup and the Omi memories API. Returns the recorded
 * Omi requests so tests can assert side effects did (not) happen.
 */
function installFetchStub({ firebaseUid }) {
  const omiRequests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes('identitytoolkit.googleapis.com')) {
      return Response.json({
        users: [{ localId: firebaseUid, providerUserInfo: [] }],
      });
    }
    omiRequests.push({ url: String(url), init });
    return Response.json({ ok: true }, { status: 200 });
  };
  return {
    omiRequests,
    restore() {
      globalThis.fetch = originalFetch;
    },
  };
}

function postRequest(body, headers = {}) {
  return new Request('http://localhost/test', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
}

test('POST /api/enable-plugins rejects a missing token before touching Redis', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  const redisStub = await loadRedisStub();
  redisStub.__redisState.saddCalls.length = 0;
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/enable-plugins/route.ts');
    const res = await POST(postRequest({ uid: 'user-1' }));
    assert.equal(res.status, 401);
    assert.deepEqual(await res.json(), { error: 'Unauthorized' });
    assert.deepEqual(redisStub.__redisState.saddCalls, []);
    assert.deepEqual(stub.omiRequests, []);
  } finally {
    stub.restore();
  }
});

test('POST /api/enable-plugins rejects a UID mismatch without touching Redis', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  const redisStub = await loadRedisStub();
  redisStub.__redisState.saddCalls.length = 0;
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/enable-plugins/route.ts');
    const res = await POST(
      postRequest({ uid: 'attacker' }, { authorization: 'Bearer valid-token' }),
    );
    assert.equal(res.status, 401);
    assert.deepEqual(redisStub.__redisState.saddCalls, []);
    assert.deepEqual(stub.omiRequests, []);
  } finally {
    stub.restore();
  }
});

test('POST /api/enable-plugins enables plugins for a matching verified UID', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  const redisStub = await loadRedisStub();
  redisStub.__redisState.saddCalls.length = 0;
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/enable-plugins/route.ts');
    const res = await POST(
      postRequest({ uid: 'user-1' }, { authorization: 'Bearer valid-token' }),
    );
    assert.equal(res.status, 200);
    assert.deepEqual(redisStub.__redisState.saddCalls, [
      {
        key: 'users:user-1:enabled_plugins',
        members: ['01JQJNSV0X8EN7HF0CP1JZ6MS4', '01JQ6XEB4SNXAN5642HGZ0CY4C'],
      },
    ]);
  } finally {
    stub.restore();
  }
});

test('POST /api/store-facts rejects a missing token before calling the Omi API', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  delete process.env.OMI_APP_ID;
  delete process.env.NEXT_PUBLIC_OMI_APP_ID;
  process.env.OMI_API_KEY = 'test-omi-key';
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/store-facts/route.ts');
    const res = await POST(postRequest({ uid: 'user-1', memories: ['fact'] }));
    assert.equal(res.status, 401);
    assert.deepEqual(await res.json(), { error: 'Unauthorized' });
    assert.deepEqual(stub.omiRequests, []);
  } finally {
    stub.restore();
  }
});

test('POST /api/store-facts rejects a UID mismatch before calling the Omi API', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  process.env.OMI_API_KEY = 'test-omi-key';
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/store-facts/route.ts');
    const res = await POST(
      postRequest(
        { uid: 'attacker', memories: ['fact'] },
        { authorization: 'Bearer valid-token' },
      ),
    );
    assert.equal(res.status, 401);
    assert.deepEqual(stub.omiRequests, []);
  } finally {
    stub.restore();
  }
});

test('POST /api/store-facts stores facts for a matching verified UID', async () => {
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY = 'test-firebase-key';
  process.env.OMI_APP_ID = 'test-app-id';
  process.env.OMI_API_KEY = 'test-omi-key';
  const stub = installFetchStub({ firebaseUid: 'user-1' });
  try {
    const { POST } = await loadRouteHandler('../../app/api/store-facts/route.ts');
    const res = await POST(
      postRequest(
        { uid: 'user-1', memories: ['likes tea'] },
        { authorization: 'Bearer valid-token' },
      ),
    );
    assert.equal(res.status, 200);
    const payload = await res.json();
    assert.equal(payload.results.length, 1);
    assert.equal(payload.results[0].success, true);
    assert.equal(stub.omiRequests.length, 1);
    assert.ok(
      stub.omiRequests[0].url.includes(
        '/v2/integrations/test-app-id/user/memories?uid=user-1',
      ),
    );
    assert.equal(stub.omiRequests[0].init.headers.Authorization, 'Bearer test-omi-key');
    assert.deepEqual(JSON.parse(stub.omiRequests[0].init.body), {
      text: 'likes tea',
      text_source: 'other',
    });
  } finally {
    stub.restore();
  }
});
