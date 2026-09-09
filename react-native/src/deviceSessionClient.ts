import {encodeBase64} from './base64';
import {isOptionalCaptureTimestamp} from './captureTimestamp';
import type {NativeHttpResponse, OmiBackend} from './omiNativeTypes';
import {
  parseRecordingTranscript,
  type RecordingTranscript,
} from './recordingTranscriptContract';

export type DeviceSessionRecord = {
  capturedAtMs?: number;
  id: string;
  deviceId: string;
  deviceName: string | null;
  codec: number;
  state: 'open' | 'complete' | 'failed';
  byteCount: number;
  chunkCount: number;
  startedAt: number;
  endedAt: number | null;
};

export class DeviceSessionBackendError extends Error {
  constructor(readonly status: number, readonly backendCode: string) {
    super(`Device session backend failed (${status}:${backendCode})`);
  }
}

function parseObject(body: string | null): Record<string, unknown> {
  if (body === null) {
    throw new Error('Backend returned an empty response');
  }
  const value: unknown = JSON.parse(body);
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Backend returned a non-object response');
  }
  return value as Record<string, unknown>;
}

function parseSession(value: unknown): DeviceSessionRecord {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Backend returned a non-object session');
  }
  const item = value as Record<string, unknown>;
  if (typeof item.transcript === 'string') {
    throw new Error('Device session response invented a transcript');
  }
  if (
    !isOptionalCaptureTimestamp(item.capturedAtMs) ||
    typeof item.id !== 'string' ||
    typeof item.deviceId !== 'string' ||
    (item.deviceName !== null && typeof item.deviceName !== 'string') ||
    !Number.isSafeInteger(item.codec) ||
    (item.codec as number) < 0 ||
    (item.codec as number) > 255 ||
    (item.state !== 'open' &&
      item.state !== 'complete' &&
      item.state !== 'failed') ||
    !Number.isSafeInteger(item.byteCount) ||
    (item.byteCount as number) < 0 ||
    !Number.isSafeInteger(item.chunkCount) ||
    (item.chunkCount as number) < 0 ||
    !Number.isSafeInteger(item.startedAt) ||
    (item.startedAt as number) < 0 ||
    (item.endedAt !== null &&
      (!Number.isSafeInteger(item.endedAt) || (item.endedAt as number) < 0))
  ) {
    throw new Error('Device session response is incomplete');
  }
  return {
    ...(item.capturedAtMs === undefined
      ? {}
      : {capturedAtMs: item.capturedAtMs}),
    id: item.id,
    deviceId: item.deviceId,
    deviceName: item.deviceName,
    codec: item.codec as number,
    state: item.state,
    byteCount: item.byteCount as number,
    chunkCount: item.chunkCount as number,
    startedAt: item.startedAt as number,
    endedAt: item.endedAt as number | null,
  };
}

function rejectIfUnusable(response: NativeHttpResponse): void {
  if (response.status >= 200 && response.status < 300) {
    return;
  }
  let backendCode = 'unknown';
  try {
    const body = parseObject(response.body);
    const error = body.error;
    if (
      error !== null &&
      typeof error === 'object' &&
      !Array.isArray(error) &&
      typeof (error as {code?: unknown}).code === 'string'
    ) {
      backendCode = (error as {code: string}).code;
    }
  } catch {
    backendCode = 'unknown';
  }
  throw new DeviceSessionBackendError(response.status, backendCode);
}

export async function openDeviceSession(
  backend: OmiBackend,
  input: {
    capturedAtMs?: number;
    captureId: string;
    deviceId: string;
    deviceName?: string;
    codec: number;
  },
): Promise<DeviceSessionRecord> {
  if (
    !isOptionalCaptureTimestamp(input.capturedAtMs) ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      input.captureId,
    )
  ) {
    throw new Error('Invalid recording identity');
  }
  const response = await backend.request({
    id: `device-session-open-${input.captureId}`,
    method: 'POST',
    path: '/v1/device-sessions',
    body: JSON.stringify({
      ...(input.capturedAtMs === undefined
        ? {}
        : {capturedAtMs: input.capturedAtMs}),
      captureId: input.captureId,
      deviceId: input.deviceId,
      ...(input.deviceName !== undefined ? {deviceName: input.deviceName} : {}),
      codec: input.codec,
    }),
  });
  rejectIfUnusable(response);
  const session = parseSession(parseObject(response.body).session);
  if (
    session.capturedAtMs !== input.capturedAtMs ||
    session.deviceId !== input.deviceId ||
    session.codec !== input.codec ||
    session.deviceName !== (input.deviceName ?? null) ||
    session.state === 'failed'
  ) {
    throw new Error('Backend did not acknowledge the recording identity');
  }
  return session;
}

export async function appendDeviceSessionAudio(
  backend: OmiBackend,
  sessionId: string,
  packets: readonly Uint8Array[],
  chunkIndex: number,
): Promise<DeviceSessionRecord> {
  const byteCount = packets.reduce((total, packet) => total + packet.length, 0);
  if (
    !Number.isSafeInteger(chunkIndex) ||
    chunkIndex < 0 ||
    packets.length < 1 ||
    packets.length > 128 ||
    chunkIndex + packets.length > 65536 ||
    byteCount > 1048576 ||
    packets.some(packet => packet.length === 0)
  ) {
    throw new Error('Invalid audio packet batch');
  }
  const body = JSON.stringify({
    chunks: packets.map((bytes, offset) => ({
      chunkIndex: chunkIndex + offset,
      bytesBase64: encodeBase64(bytes),
    })),
  });
  if (body.length > 2097152)
    throw new Error('Audio packet batch exceeds request limit');
  const response = await backend.request({
    id: `device-session-audio-${sessionId}-${chunkIndex}-${packets.length}`,
    method: 'POST',
    path: `/v1/device-sessions/${sessionId}/audio`,
    body,
  });
  rejectIfUnusable(response);
  const session = parseSession(parseObject(response.body).session);
  if (
    session.id !== sessionId ||
    session.chunkCount < chunkIndex + packets.length ||
    session.byteCount < byteCount ||
    session.state === 'failed'
  ) {
    throw new Error('Backend did not acknowledge the audio batch');
  }
  return session;
}

export async function completeDeviceSession(
  backend: OmiBackend,
  sessionId: string,
): Promise<DeviceSessionRecord> {
  const response = await backend.request({
    id: `device-session-complete-${sessionId}`,
    method: 'POST',
    path: `/v1/device-sessions/${sessionId}/complete`,
  });
  rejectIfUnusable(response);
  const session = parseSession(parseObject(response.body).session);
  if (session.id !== sessionId || session.state !== 'complete') {
    throw new Error('Backend did not acknowledge recording completion');
  }
  return session;
}

export function isTransientDeviceSessionError(error: unknown): boolean {
  if (error instanceof DeviceSessionBackendError) {
    return [0, 408, 429, 500, 502, 503, 504].includes(error.status);
  }
  return (
    error instanceof TypeError ||
    (error !== null &&
      typeof error === 'object' &&
      'code' in error &&
      error.code === 'OMI_HTTP_TRANSPORT')
  );
}

export async function transcribeDeviceSession(
  backend: OmiBackend,
  sessionId: string,
): Promise<RecordingTranscript> {
  const response = await backend.request({
    id: `device-session-transcribe-${sessionId}`,
    method: 'POST',
    path: `/v1/device-sessions/${encodeURIComponent(sessionId)}/transcribe`,
  });
  rejectIfUnusable(response);
  const transcript =
    response.status === 200 || response.status === 202
      ? parseRecordingTranscript(response.body, sessionId)
      : null;
  if (transcript === null)
    throw new Error('Backend did not acknowledge transcription');
  return transcript;
}
