import {Platform} from 'react-native';

import type {NativeHttpResponse, OmiBackend} from './omiNativeTypes';
import type {LiveVoiceProvider} from './desktopSettingsClient';
import {resolveNativeLiveWebRtcScope} from './liveWebRtcNative';

// Live session minting. The Worker holds provider keys; this client only ever
// sends a provider choice (plus an SDP offer for GPT Live 1) and receives a
// transport answer. No secret ever reaches JavaScript.
export const LIVE_SESSION_PATH = '/v1/live/sessions';
export const LIVE_MODEL = 'gpt-live-1';
export const GEMINI_LIVE_MODEL = 'models/gemini-3.1-flash-live-preview';

export type {LiveVoiceProvider};

export type GptLiveSession = {
  provider: 'gpt_live';
  sessionId: string;
  answerSdp: string;
};

export type GeminiLiveSession = {
  provider: 'gemini_live';
  sessionId: string;
  token: string;
  model: string;
  url: string;
};

export type LiveSession = GptLiveSession | GeminiLiveSession;

export class LiveSessionBackendError extends Error {
  constructor(
    readonly status: number,
    readonly backendCode: string,
    readonly retryable: boolean,
    readonly action: string,
    readonly provider?: LiveVoiceProvider,
  ) {
    super(`Live session backend failed (${status}:${backendCode})`);
  }
}

export class LiveUnsupportedError extends Error {
  constructor(message = 'Live voice needs WebRTC on this device.') {
    super(message);
    this.name = 'LiveUnsupportedError';
  }
}

export function liveErrorCopy(
  error: unknown,
  provider: LiveVoiceProvider = 'gpt_live',
): string {
  if (error instanceof LiveUnsupportedError) {
    return error.message;
  }
  if (!(error instanceof LiveSessionBackendError)) {
    return provider === 'gemini_live'
      ? 'Gemini Live could not start. Check your connection and try again.'
      : 'Live voice could not start. Check your connection and try again.';
  }
  if (error.action === 'reauthenticate' || error.status === 401) {
    return 'Sign in again to use Live voice.';
  }
  if (error.backendCode === 'provider_not_configured') {
    return provider === 'gemini_live'
      ? 'Gemini Live is not configured on this server yet (missing GEMINI_API_KEY).'
      : 'GPT Live 1 is not configured on this server yet (missing OPENAI_API_KEY).';
  }
  if (error.status === 503 || error.retryable) {
    return provider === 'gemini_live'
      ? 'Gemini Live is temporarily unavailable. Try again.'
      : 'Live voice is temporarily unavailable. Try again.';
  }
  return provider === 'gemini_live'
    ? 'Gemini Live could not start on this device.'
    : 'Live voice could not start on this device.';
}

export function liveWebRtcSupported(): boolean {
  if (Platform.OS === 'macos') {
    return false;
  }
  if (Platform.OS === 'ios' || Platform.OS === 'android') {
    return resolveNativeLiveWebRtcScope() !== null;
  }
  const scope = globalThis as {
    RTCPeerConnection?: unknown;
    navigator?: {mediaDevices?: {getUserMedia?: unknown}};
  };
  return (
    typeof scope.RTCPeerConnection === 'function' &&
    typeof scope.navigator?.mediaDevices?.getUserMedia === 'function'
  );
}

export function liveGeminiSupported(): boolean {
  const scope = globalThis as {
    WebSocket?: unknown;
    AudioContext?: unknown;
    webkitAudioContext?: unknown;
    navigator?: {mediaDevices?: {getUserMedia?: unknown}};
  };
  const hasAudioContext =
    typeof scope.AudioContext === 'function' ||
    typeof scope.webkitAudioContext === 'function';
  return (
    typeof scope.WebSocket === 'function' &&
    hasAudioContext &&
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
  if (
    typeof sessionId !== 'string' ||
    sessionId.length === 0 ||
    sessionId.length > 256
  ) {
    throw new Error('Live session response is incomplete');
  }

  if (transportType === 'gemini_ws' || record.provider === 'gemini_live') {
    const token = (transport as Record<string, unknown>).token;
    const model = (transport as Record<string, unknown>).model;
    const url = (transport as Record<string, unknown>).url;
    if (
      typeof token !== 'string' ||
      token.length === 0 ||
      token.length > 2048 ||
      typeof model !== 'string' ||
      model.length === 0 ||
      typeof url !== 'string' ||
      !url.startsWith('wss://')
    ) {
      throw new Error('Live session response is incomplete');
    }
    return {
      provider: 'gemini_live',
      sessionId,
      token,
      model,
      url,
    };
  }

  if (transportType !== undefined && transportType !== 'webrtc') {
    throw new Error('Live session response used an unsupported transport');
  }
  const answerSdp = (transport as Record<string, unknown>).sdp;
  if (typeof answerSdp !== 'string' || answerSdp.length === 0) {
    throw new Error('Live session response is incomplete');
  }
  return {provider: 'gpt_live', sessionId, answerSdp};
}

export type LiveSessionRequest =
  | {provider: 'gpt_live'; sdp: string}
  | {provider: 'gemini_live'};

export async function requestLiveSession(
  backend: OmiBackend,
  input: LiveSessionRequest | string,
): Promise<LiveSession> {
  // Backward compatible: a bare SDP string is GPT Live 1.
  const request: LiveSessionRequest =
    typeof input === 'string' ? {provider: 'gpt_live', sdp: input} : input;
  if (request.provider === 'gpt_live') {
    if (typeof request.sdp !== 'string' || request.sdp.trim().length === 0) {
      throw new Error('An SDP offer is required');
    }
  }
  const body =
    request.provider === 'gpt_live'
      ? JSON.stringify({provider: 'gpt_live', sdp: request.sdp})
      : JSON.stringify({provider: 'gemini_live'});
  const response = await backend.request({
    id: 'live-session',
    method: 'POST',
    path: LIVE_SESSION_PATH,
    body,
  });
  if (response.status !== 200 && response.status !== 201) {
    throwBackendError(response, request.provider);
  }
  return parseLiveSession(response.body);
}

function throwBackendError(
  response: NativeHttpResponse,
  provider: LiveVoiceProvider,
): never {
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
  throw new LiveSessionBackendError(
    response.status,
    code,
    retryable,
    action,
    provider,
  );
}
