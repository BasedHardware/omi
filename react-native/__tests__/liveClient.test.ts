import {
  LIVE_SESSION_PATH,
  LiveSessionBackendError,
  liveErrorCopy,
  liveGeminiSupported,
  liveWebRtcSupported,
  parseLiveSession,
  requestLiveSession,
} from '../src/liveClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';

function backend(
  handler: (request: NativeHttpRequest) => {
    status: number;
    body: string | null;
  },
): OmiBackend {
  return {
    createRecordingId: async () => 'capture',
    request: async (request: NativeHttpRequest) => {
      const result = handler(request);
      return {
        id: request.id,
        status: result.status,
        body: result.body,
      };
    },
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
}

const answer = JSON.stringify({
  provider: 'gpt_live',
  session: {id: 'live_123'},
  transport: {type: 'webrtc', sdp: 'v=0\r\na=answer\r\n'},
});

const geminiAnswer = JSON.stringify({
  provider: 'gemini_live',
  session: {id: 'gem_123'},
  transport: {
    type: 'gemini_ws',
    token: 'auth_tokens/ephemeral',
    model: 'models/gemini-3.1-flash-live-preview',
    url: 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained',
  },
});

test('posts the SDP offer to the authenticated live route and parses the answer', async () => {
  const requests: NativeHttpRequest[] = [];
  const response = await requestLiveSession(
    backend(request => {
      requests.push(request);
      return {status: 201, body: answer};
    }),
    {provider: 'gpt_live', sdp: 'v=0\r\no=- offer\r\n'},
  );
  expect(response).toEqual({
    provider: 'gpt_live',
    sessionId: 'live_123',
    answerSdp: 'v=0\r\na=answer\r\n',
  });
  expect(requests).toHaveLength(1);
  expect(requests[0]?.method).toBe('POST');
  expect(requests[0]?.path).toBe('/v1/live/sessions');
  expect(requests[0]?.path).toBe(LIVE_SESSION_PATH);
  expect(JSON.parse(requests[0]?.body ?? '{}')).toEqual({
    provider: 'gpt_live',
    sdp: 'v=0\r\no=- offer\r\n',
  });
});

test('posts gemini_live without an SDP offer and parses the ws transport', async () => {
  const requests: NativeHttpRequest[] = [];
  const response = await requestLiveSession(
    backend(request => {
      requests.push(request);
      return {status: 201, body: geminiAnswer};
    }),
    {provider: 'gemini_live'},
  );
  expect(response.provider).toBe('gemini_live');
  if (response.provider === 'gemini_live') {
    expect(response.token).toBe('auth_tokens/ephemeral');
    expect(response.model).toBe('models/gemini-3.1-flash-live-preview');
    expect(response.url.startsWith('wss://')).toBe(true);
    expect(response.url).not.toContain('key=');
  }
  expect(JSON.parse(requests[0]?.body ?? '{}')).toEqual({
    provider: 'gemini_live',
  });
});

test('rejects empty offers without touching the transport', async () => {
  let calls = 0;
  await expect(
    requestLiveSession(
      backend(() => {
        calls += 1;
        return {status: 201, body: answer};
      }),
      {provider: 'gpt_live', sdp: '   '},
    ),
  ).rejects.toThrow('An SDP offer is required');
  expect(calls).toBe(0);
});

test('surfaces a retryable provider-not-configured error from the worker', async () => {
  const error = JSON.stringify({
    error: {code: 'provider_not_configured', retryable: true, action: 'retry'},
  });
  try {
    await requestLiveSession(
      backend(() => ({status: 503, body: error})),
      {provider: 'gpt_live', sdp: 'v=0\r\n'},
    );
    throw new Error('expected requestLiveSession to throw');
  } catch (caught) {
    expect(caught).toBeInstanceOf(LiveSessionBackendError);
    if (caught instanceof LiveSessionBackendError) {
      expect(caught.status).toBe(503);
      expect(caught.backendCode).toBe('provider_not_configured');
      expect(caught.retryable).toBe(true);
    }
    expect(liveErrorCopy(caught, 'gpt_live')).toBe(
      'GPT Live 1 is not configured on this server yet (missing OPENAI_API_KEY).',
    );
    expect(liveErrorCopy(caught, 'gemini_live')).toBe(
      'Gemini Live is not configured on this server yet (missing GEMINI_API_KEY).',
    );
  }
});

test('maps a 401 to a sign-in prompt', async () => {
  const error = JSON.stringify({
    error: {code: 'unauthorized', retryable: false, action: 'reauthenticate'},
  });
  try {
    await requestLiveSession(
      backend(() => ({status: 401, body: error})),
      {provider: 'gpt_live', sdp: 'v=0\r\n'},
    );
    throw new Error('expected requestLiveSession to throw');
  } catch (caught) {
    expect(liveErrorCopy(caught)).toBe('Sign in again to use Live voice.');
  }
});

test('rejects malformed or wrong-transport answers', () => {
  expect(() => parseLiveSession(null)).toThrow('empty');
  expect(() => parseLiveSession('{}')).toThrow('incomplete');
  expect(() =>
    parseLiveSession(
      JSON.stringify({
        session: {id: 'live_1'},
        transport: {type: 'websocket', sdp: 'x'},
      }),
    ),
  ).toThrow('unsupported transport');
  expect(() =>
    parseLiveSession(
      JSON.stringify({session: {}, transport: {type: 'webrtc', sdp: 'x'}}),
    ),
  ).toThrow('incomplete');
  expect(() =>
    parseLiveSession(
      JSON.stringify({
        provider: 'gemini_live',
        session: {id: 'g1'},
        transport: {type: 'gemini_ws', token: '', model: 'm', url: 'wss://x'},
      }),
    ),
  ).toThrow('incomplete');
});

test('reports WebRTC and Gemini availability from the runtime scope', () => {
  const {Platform} = require('react-native');
  const previousOS = Platform.OS;
  const scope = globalThis as {
    RTCPeerConnection?: unknown;
    WebSocket?: unknown;
    AudioContext?: unknown;
    navigator?: {mediaDevices?: {getUserMedia?: unknown}};
  };
  const previous = {
    peer: scope.RTCPeerConnection,
    webSocket: scope.WebSocket,
    audio: scope.AudioContext,
    mediaDevices: scope.navigator?.mediaDevices,
  };
  try {
    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
    delete scope.RTCPeerConnection;
    expect(liveWebRtcSupported()).toBe(false);
    scope.RTCPeerConnection = class {};
    scope.navigator = {mediaDevices: {getUserMedia: () => undefined}};
    expect(liveWebRtcSupported()).toBe(true);

    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'macos'});
    expect(liveWebRtcSupported()).toBe(false);

    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'ios'});
    expect(liveWebRtcSupported()).toBe(true);

    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
    delete scope.WebSocket;
    delete scope.AudioContext;
    expect(liveGeminiSupported()).toBe(false);
    scope.WebSocket = class {};
    scope.AudioContext = class {};
    expect(liveGeminiSupported()).toBe(true);
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: previousOS,
    });
    if (previous.peer === undefined) {
      delete scope.RTCPeerConnection;
    } else {
      scope.RTCPeerConnection = previous.peer;
    }
    if (previous.webSocket === undefined) {
      delete scope.WebSocket;
    } else {
      scope.WebSocket = previous.webSocket;
    }
    if (previous.audio === undefined) {
      delete scope.AudioContext;
    } else {
      scope.AudioContext = previous.audio;
    }
    if (previous.mediaDevices === undefined) {
      delete scope.navigator;
    }
  }
});
