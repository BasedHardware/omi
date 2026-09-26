import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PERSONA_CHAT_LANES,
  PersonaAuthenticationError,
  PersonaGatewayUnavailableError,
  personaLaneForIdentity,
  requestPersonaChatStream,
  resolvePersonaIdentity,
} from './persona-chat-gateway.mjs';

const okStreamResponse = () =>
  new Response('data: {"choices":[{"delta":{"content":"hi"}}]}\n\n', {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });

test('missing authentication is pinned to the GPT-5.4 nano persona lane', async () => {
  let request;
  const response = await requestPersonaChatStream({
    identity: await resolvePersonaIdentity(null),
    messages: [{ role: 'user', content: 'hello' }],
    gatewayUrl: 'http://gateway.internal',
    gatewayToken: 'service-token',
    requestedModel: 'anthropic/claude-opus-5',
    fetchImpl: async (url, init) => {
      request = { url, init };
      return okStreamResponse();
    },
  });

  assert.equal(response.status, 200);
  assert.equal(JSON.parse(request.init.body).model, PERSONA_CHAT_LANES.unauthenticated);
  assert.equal(request.init.headers['X-Omi-LLM-Feature'], 'persona_chat');
  assert.equal(request.init.headers['X-Omi-User-Uid'], undefined);
});

test('verified non-anonymous authentication is pinned to the GPT-5.6 Luna persona lane', async () => {
  const identity = await resolvePersonaIdentity('Bearer valid-token', {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({
        users: [
          { localId: 'verified-uid', providerUserInfo: [{ providerId: 'google.com' }] },
        ],
      }),
  });
  let request;

  await requestPersonaChatStream({
    identity,
    messages: [{ role: 'user', content: 'hello' }],
    gatewayUrl: 'http://gateway.internal/',
    gatewayToken: 'service-token',
    fetchImpl: async (url, init) => {
      request = { url, init };
      return okStreamResponse();
    },
  });

  assert.equal(JSON.parse(request.init.body).model, PERSONA_CHAT_LANES.authenticated);
  assert.equal(request.init.headers['X-Omi-LLM-Feature'], 'persona_chat_premium');
  assert.equal(request.init.headers['X-Omi-User-Uid'], 'verified-uid');
});

test('anonymous Firebase identities stay on the unauthenticated lane', async () => {
  const identity = await resolvePersonaIdentity('Bearer anonymous-token', {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({ users: [{ localId: 'anonymous-uid', providerUserInfo: [] }] }),
  });

  assert.equal(identity, null);
});

test('malformed or rejected authentication fails closed', async () => {
  await assert.rejects(
    resolvePersonaIdentity('authenticated=true'),
    PersonaAuthenticationError,
  );
  await assert.rejects(
    resolvePersonaIdentity('Bearer spoofed-token', {
      firebaseApiKey: 'firebase-public-key',
      fetchImpl: async () => new Response('{}', { status: 401 }),
    }),
    PersonaAuthenticationError,
  );
});

test('gateway failure never invokes a provider fallback', async () => {
  let calls = 0;
  await assert.rejects(
    requestPersonaChatStream({
      identity: null,
      messages: [{ role: 'user', content: 'hello' }],
      gatewayUrl: 'http://gateway.internal',
      gatewayToken: 'service-token',
      fetchImpl: async (url) => {
        calls += 1;
        assert.equal(url, 'http://gateway.internal/v1/chat/completions');
        return new Response('{}', { status: 503 });
      },
    }),
    PersonaGatewayUnavailableError,
  );
  assert.equal(calls, 1);
});

test('missing gateway URL or service token fails closed before a request is sent', async () => {
  for (const { gatewayUrl, gatewayToken } of [
    { gatewayUrl: '', gatewayToken: 'service-token' },
    { gatewayUrl: 'http://gateway.internal', gatewayToken: '  ' },
  ]) {
    let calls = 0;
    await assert.rejects(
      requestPersonaChatStream({
        identity: null,
        messages: [{ role: 'user', content: 'hello' }],
        gatewayUrl,
        gatewayToken,
        fetchImpl: async () => {
          calls += 1;
          return okStreamResponse();
        },
      }),
      PersonaGatewayUnavailableError,
    );
    assert.equal(calls, 0);
  }
});

test('personaLaneForIdentity returns the correct lane for valid and null identities', () => {
  assert.equal(PERSONA_CHAT_LANES.unauthenticated, 'omi:auto:persona-chat');
  assert.equal(PERSONA_CHAT_LANES.authenticated, 'omi:auto:persona-chat-premium');
  assert.equal(personaLaneForIdentity(null), PERSONA_CHAT_LANES.unauthenticated);
  assert.equal(personaLaneForIdentity(undefined), PERSONA_CHAT_LANES.unauthenticated);
  assert.equal(
    personaLaneForIdentity({ uid: 'test-user' }),
    PERSONA_CHAT_LANES.authenticated,
  );
});
