import type {NativeHttpResponse, OmiBackend} from './omiNative';

export type DeviceSessionRecord = {
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

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index] ?? 0);
  }
  return globalThis.btoa(binary);
}

export async function openDeviceSession(
  backend: OmiBackend,
  input: {deviceId: string; deviceName?: string; codec: number},
): Promise<DeviceSessionRecord> {
  const response = await backend.request({
    id: `device-session-open-${input.deviceId}`,
    method: 'POST',
    path: '/v1/device-sessions',
    body: JSON.stringify({
      deviceId: input.deviceId,
      ...(input.deviceName !== undefined ? {deviceName: input.deviceName} : {}),
      codec: input.codec,
    }),
  });
  rejectIfUnusable(response);
  return parseSession(parseObject(response.body).session);
}

export async function appendDeviceSessionAudio(
  backend: OmiBackend,
  sessionId: string,
  bytes: Uint8Array,
  chunkIndex: number,
): Promise<DeviceSessionRecord> {
  if (
    !Number.isSafeInteger(chunkIndex) ||
    chunkIndex < 0 ||
    chunkIndex > 65535
  ) {
    throw new Error('Invalid audio chunk index');
  }
  const response = await backend.request({
    id: `device-session-audio-${sessionId}-${chunkIndex}`,
    method: 'POST',
    path: `/v1/device-sessions/${sessionId}/audio`,
    body: JSON.stringify({bytesBase64: bytesToBase64(bytes), chunkIndex}),
  });
  rejectIfUnusable(response);
  const session = parseSession(parseObject(response.body).session);
  if (
    session.id !== sessionId ||
    session.chunkCount <= chunkIndex ||
    session.byteCount < bytes.length ||
    session.state === 'failed'
  ) {
    throw new Error('Backend did not acknowledge the audio chunk');
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
