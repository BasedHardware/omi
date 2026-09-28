import type {OmiBackend} from './omiNative';

export type MemoryVisibility = 'public' | 'private';
export type LegacyWriteFailure =
  | {kind: 'auth-invalid'; detail: string}
  | {kind: 'rate-limited'; retryAfterMs: number; detail: string}
  | {kind: 'permanent'; status: number; detail: string}
  | {kind: 'unknown'; detail: string};
export type LegacyWriteResult<T = void> =
  | {ok: true; value: T}
  | {ok: false; failure: LegacyWriteFailure};

export type CreatedMemory = Record<string, unknown> & {id: string};

function failure(status: number): LegacyWriteFailure {
  if (status === 401)
    return {kind: 'auth-invalid', detail: 'Sign in before changing memories'};
  if (status === 429)
    return {
      kind: 'rate-limited',
      retryAfterMs: 1000,
      detail: 'Wait before changing memories again',
    };
  if ([400, 403, 404, 409, 422].includes(status))
    return {
      kind: 'permanent',
      status,
      detail: 'The service did not accept this memory change',
    };
  return {
    kind: 'unknown',
    detail: 'The memory change could not be confirmed',
  };
}

async function requestMemoryWrite(
  backend: OmiBackend,
  method: 'POST' | 'PATCH' | 'DELETE',
  path: `/${string}`,
  body?: string,
): Promise<LegacyWriteResult<unknown>> {
  try {
    if ((await backend.getApiContract?.()) !== 'omi') {
      return {
        ok: false,
        failure: {
          kind: 'permanent',
          status: 409,
          detail: 'Memory changes require the legacy Omi backend',
        },
      };
    }
    const response = await backend.request({
      id: `omi-memory-${method.toLowerCase()}`,
      method,
      expectedApiContract: 'omi',
      path,
      ...(body === undefined ? {} : {body}),
    });
    if (method === 'DELETE' && response.status === 404)
      return {ok: true, value: undefined};
    if (response.status !== 200) {
      if (response.status === 429) {
        const seconds = response.retryAfterSeconds;
        return {
          ok: false,
          failure: {
            kind: 'rate-limited',
            retryAfterMs:
              typeof seconds === 'number' &&
              Number.isFinite(seconds) &&
              seconds >= 0
                ? seconds * 1000
                : 1000,
            detail: 'Wait before changing memories again',
          },
        };
      }
      const result = failure(response.status);
      return {ok: false, failure: result};
    }
    if (method === 'DELETE') return {ok: true, value: undefined};
    if (response.body === null)
      return {
        ok: false,
        failure: {
          kind: 'unknown',
          detail: 'The memory change returned no confirmation',
        },
      };
    try {
      return {ok: true, value: JSON.parse(response.body) as unknown};
    } catch {
      return {
        ok: false,
        failure: {
          kind: 'unknown',
          detail: 'The memory change returned an invalid response',
        },
      };
    }
  } catch {
    return {
      ok: false,
      failure: {
        kind: 'unknown',
        detail: 'The memory change could not be confirmed',
      },
    };
  }
}

export async function createMemory(
  backend: OmiBackend,
  content: string,
): Promise<LegacyWriteResult<CreatedMemory>> {
  const result = await requestMemoryWrite(
    backend,
    'POST',
    '/v3/memories',
    JSON.stringify({
      content,
      category: 'manual',
      visibility: 'private',
      tags: [],
    }),
  );
  if (!result.ok) return result;
  const value = result.value;
  if (
    value === null ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    typeof (value as Record<string, unknown>).id !== 'string'
  )
    return {
      ok: false,
      failure: {
        kind: 'unknown',
        detail: 'The created memory could not be identified',
      },
    };
  return {ok: true, value: value as CreatedMemory};
}

export function editMemory(
  backend: OmiBackend,
  id: string,
  content: string,
): Promise<LegacyWriteResult<unknown>> {
  return requestMemoryWrite(
    backend,
    'PATCH',
    `/v3/memories/${encodeURIComponent(id)}`,
    JSON.stringify({value: content}),
  );
}

export async function deleteMemory(
  backend: OmiBackend,
  id: string,
): Promise<LegacyWriteResult> {
  const result = await requestMemoryWrite(
    backend,
    'DELETE',
    `/v3/memories/${encodeURIComponent(id)}`,
  );
  return result.ok ? {ok: true, value: undefined} : result;
}

export function setMemoryVisibility(
  backend: OmiBackend,
  id: string,
  visibility: MemoryVisibility,
): Promise<LegacyWriteResult<unknown>> {
  return requestMemoryWrite(
    backend,
    'PATCH',
    `/v3/memories/${encodeURIComponent(id)}/visibility`,
    JSON.stringify({value: visibility}),
  );
}
