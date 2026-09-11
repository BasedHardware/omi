import type {NativeHttpResponse, OmiBackend} from './omiNativeTypes';

// GPT-Live-1 session minting. The Worker holds the OpenAI project key; this
// client only ever sends an SDP offer and receives an SDP answer plus the
// opaque session id. No secret ever reaches JavaScript.
export const LIVE_SESSION_PATH = '/v1/live/sessions';
export const LIVE_MODEL = 'gpt-live-1';

export type LiveSession = {
  sessionId: string;
  answerSdp: string;
};

export class LiveSessionBackendError extends Error {
  constructor(
    readonly status: number,
    readonly backendCode: string,
    readonly retryable: boolean,
    readonly action: string,
  ) {
    super(`Live session backend failed (${status}:${backendCode})`);
  }
}

export class LiveUnsupportedError extends Error {
  constructor() {
    super('Live voice needs WebRTC on this device.');
    this.name = 'LiveUnsupportedError';
  }
}

export function liveErrorCopy(error: unknown): string {
  if (error instanceof LiveUnsupportedError) {
    return error.message;
  }
  if (!(error instanceof LiveSessionBackendError)) {
    return 'Live voice could not start. Check your connection and try again.';
  }
  if (error.action === 'reauthenticate' || error.status === 401) {
    return 'Sign in again to use Live voice.';
  }
  if (error.backendCode === 'provider_not_configured') {
    return 'Live voice is not configured on this server yet.';
  }
  if (error.status === 503 || error.retryable) {
    return 'Live voice is temporarily unavailable. Try again.';
  }
  return 'Live voice could not start on this device.';
}

export function liveWebRtcSupported(): boolean {
  const scope = globalThis as {
    RTCPeerConnection?: unknown;
    navigator?: {mediaDevices?: {getUserMedia?: unknown}};
  };
  return (
    typeof scope.RTCPeerConnection === 'function' &&
    typeof scope.navigator?.mediaDevices?.getUserMedia === 'function'
  );
}

export function parseLiveSession(body: string | null): LiveSession {
  if (body === null) {
    throw new Error('Live session response is empty');
  }
  const value: unknown = JSON.parse(body);
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Live session response is malformed');
  }
  const record = value as Record<string, unknown>;
  const session = record.session;
  const transport = record.transport;
  if (
    session === null ||
    typeof session !== 'object' ||
    Array.isArray(session) ||
    transport === null ||
    typeof transport !== 'object' ||
    Array.isArray(transport)
  ) {
    throw new Error('Live session response is incomplete');
  }
  const sessionId = (session as Record<string, unknown>).id;
  const transportType = (transport as Record<string, unknown>).type;
  const answerSdp = (transport as Record<string, unknown>).sdp;
  if (transportType !== undefined && transportType !== 'webrtc') {
    throw new Error('Live session response used an unsupported transport');
  }
  if (
    typeof sessionId !== 'string' ||
    sessionId.length === 0 ||
    sessionId.length > 256 ||
    typeof answerSdp !== 'string' ||
    answerSdp.length === 0
  ) {
    throw new Error('Live session response is incomplete');
  }
  return {sessionId, answerSdp};
}

export async function requestLiveSession(
  backend: OmiBackend,
  sdp: string,
): Promise<LiveSession> {
  if (typeof sdp !== 'string' || sdp.trim().length === 0) {
    throw new Error('An SDP offer is required');
  }
  const response = await backend.request({
    id: 'live-session',
    method: 'POST',
    path: LIVE_SESSION_PATH,
    body: JSON.stringify({sdp}),
  });
  if (response.status !== 200 && response.status !== 201) {
    throwBackendError(response);
  }
  return parseLiveSession(response.body);
}

function throwBackendError(response: NativeHttpResponse): never {
  let code = 'unknown';
  let retryable = false;
  let action = 'none';
  if (response.body !== null) {
    try {
      const parsed = JSON.parse(response.body) as {
        error?: {code?: unknown; retryable?: unknown; action?: unknown};
      };
      if (typeof parsed.error?.code === 'string') {
        code = parsed.error.code;
      }
      if (typeof parsed.error?.retryable === 'boolean') {
        retryable = parsed.error.retryable;
      }
      if (typeof parsed.error?.action === 'string') {
        action = parsed.error.action;
      }
    } catch {}
  }
  throw new LiveSessionBackendError(response.status, code, retryable, action);
}
