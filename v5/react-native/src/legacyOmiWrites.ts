import type {OmiBackend, NativeHttpResponse} from './omiNativeTypes';

export type LegacyWriteFailure =
  | {kind: 'auth-invalid'; detail: string}
  | {kind: 'rate-limited'; retryAfterMs: number; detail: string}
  | {
      kind: 'permanent';
      reason: 'conflict' | 'gone' | 'validation';
      detail: string;
    }
  | {kind: 'retryable'; unclassified: true; detail: string};

export type LegacyWriteResult<T = unknown> =
  | {ok: true; value: T}
  | {ok: false; failure: LegacyWriteFailure};

type WriteRequest = {
  id: string;
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  path: `/${string}`;
  body?: string;
  timeoutSeconds?: number;
};

function classify<T>(response: NativeHttpResponse): LegacyWriteResult<T> {
  if (response.status === 401)
    return {
      ok: false,
      failure: {kind: 'auth-invalid', detail: 'Sign in again'},
    };
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
        detail: 'Wait before trying again',
      },
    };
  }
  if ([400, 403, 404, 409, 422].includes(response.status))
    return {
      ok: false,
      failure: {
        kind: 'permanent',
        reason:
          response.status === 409
            ? 'conflict'
            : response.status === 404
            ? 'gone'
            : 'validation',
        detail: 'The service did not accept this change',
      },
    };
  if (response.status < 200 || response.status >= 300)
    return {
      ok: false,
      failure: {
        kind: 'retryable',
        unclassified: true,
        detail: 'The change is unconfirmed; refresh before trying again',
      },
    };
  if (response.body === null || response.body === '')
    return {ok: true, value: undefined as T};
  try {
    return {ok: true, value: JSON.parse(response.body) as T};
  } catch {
    return {
      ok: false,
      failure: {
        kind: 'retryable',
        unclassified: true,
        detail: 'The change is unconfirmed; refresh before trying again',
      },
    };
  }
}

async function send<T>(
  backend: OmiBackend,
  request: WriteRequest,
): Promise<LegacyWriteResult<T>> {
  try {
    if ((await backend.getApiContract?.()) !== 'omi') {
      return {
        ok: false,
        failure: {
          kind: 'permanent',
          reason: 'conflict',
          detail: 'Conversation writes require the Omi API',
        },
      };
    }
    const response = await backend.request({
      ...request,
      expectedApiContract: 'omi',
    });
    return classify<T>(response);
  } catch {
    return {
      ok: false,
      failure: {
        kind: 'retryable',
        unclassified: true,
        detail: 'The change is unconfirmed; refresh before trying again',
      },
    };
  }
}

const encodedId = (id: string) => encodeURIComponent(id);

export function deleteConversation(backend: OmiBackend, id: string) {
  return send(backend, {
    id: `omi-conversation-delete-${id}`,
    method: 'DELETE',
    path: `/v1/conversations/${encodedId(id)}?cascade=true`,
  });
}

export function setConversationTitle(
  backend: OmiBackend,
  id: string,
  title: string,
) {
  return send(backend, {
    id: `omi-conversation-title-${id}`,
    method: 'PATCH',
    path: `/v1/conversations/${encodedId(id)}/title?title=${encodeURIComponent(
      title,
    )}`,
  });
}

export function reprocessConversation(
  backend: OmiBackend,
  id: string,
  options: {appId?: string; languageCode?: string} = {},
) {
  const query = new URLSearchParams();
  if (options.languageCode) query.set('language_code', options.languageCode);
  if (options.appId) query.set('app_id', options.appId);
  const suffix = query.size ? `?${query.toString()}` : '';
  return send<Record<string, unknown>>(backend, {
    id: `omi-conversation-reprocess-${id}`,
    method: 'POST',
    path: `/v1/conversations/${encodedId(id)}/reprocess${suffix}`,
    timeoutSeconds: 180,
  });
}

export function setConversationVisibility(
  backend: OmiBackend,
  id: string,
  value: 'shared' | 'private',
) {
  return send(backend, {
    id: `omi-conversation-visibility-${id}`,
    method: 'PATCH',
    path: `/v1/conversations/${encodedId(id)}/visibility?value=${value}`,
  });
}

export async function conversationShareUrl(
  backend: Pick<OmiBackend, 'createWriteId'>,
  id: string,
): Promise<string> {
  // The sid is a random per-share tag (classic uses Random.secure()), never
  // derived from the sender or content. createWriteId is the bridge CSPRNG:
  // SecRandomCopyBytes (Apple), SecureRandom (Android), WebCrypto (web).
  if (backend.createWriteId === undefined) {
    throw new Error('Share id entropy is unavailable');
  }
  const writeId = await backend.createWriteId();
  const uuidHex = writeId.replace(/[^0-9a-f]/g, '').slice(0, 32);
  if (uuidHex.length !== 32) {
    throw new Error('Share id entropy is unavailable');
  }
  return `https://h.omi.me/conversations/${encodedId(id)}?s=mac&sid=${uuidHex}`;
}

export function setConversationStarred(
  backend: OmiBackend,
  id: string,
  starred: boolean,
) {
  return send(backend, {
    id: `omi-conversation-starred-${id}`,
    method: 'PATCH',
    path: `/v1/conversations/${encodedId(id)}/starred?starred=${starred}`,
  });
}

export type LegacyFolder = {
  id: string;
  name: string;
  color?: string;
  icon?: string;
};

export async function listFolders(
  backend: OmiBackend,
): Promise<LegacyWriteResult<LegacyFolder[]>> {
  const result = await send<unknown>(backend, {
    id: 'omi-folders-list',
    method: 'GET',
    path: '/v1/folders',
  });
  if (!result.ok) return result;
  if (
    !Array.isArray(result.value) ||
    !result.value.every(
      folder =>
        folder !== null &&
        typeof folder === 'object' &&
        typeof folder.id === 'string' &&
        typeof folder.name === 'string',
    )
  ) {
    return {
      ok: false,
      failure: {
        kind: 'retryable',
        unclassified: true,
        detail: 'The folder list could not be read; refresh to try again',
      },
    };
  }
  return {
    ok: true,
    value: result.value.map(folder => ({
      id: folder.id as string,
      name: folder.name as string,
      ...(typeof folder.color === 'string' ? {color: folder.color} : {}),
      ...(typeof folder.icon === 'string' ? {icon: folder.icon} : {}),
    })),
  };
}

export function moveConversationToFolder(
  backend: OmiBackend,
  id: string,
  folderId: string | null,
) {
  return send(backend, {
    id: `omi-conversation-folder-${id}`,
    method: 'PATCH',
    path: `/v1/conversations/${encodedId(id)}/folder`,
    body: JSON.stringify({folder_id: folderId}),
  });
}

export type MemoryVisibility = 'public' | 'private';
export type CreatedMemory = Record<string, unknown> & {id: string};

const memoryPath = (id: string): `/${string}` =>
  `/v3/memories/${encodeURIComponent(id)}`;

export async function createMemory(
  backend: OmiBackend,
  content: string,
): Promise<LegacyWriteResult<CreatedMemory>> {
  const result = await send<unknown>(backend, {
    id: 'omi-memory-post',
    method: 'POST',
    path: '/v3/memories',
    body: JSON.stringify({
      content,
      category: 'manual',
      visibility: 'private',
      tags: [],
    }),
  });
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
        kind: 'retryable',
        unclassified: true,
        detail: 'The created memory could not be identified; refresh to check',
      },
    };
  return {ok: true, value: value as CreatedMemory};
}

export function editMemory(backend: OmiBackend, id: string, content: string) {
  // The server rejects any field besides `value`.
  return send(backend, {
    id: 'omi-memory-patch',
    method: 'PATCH',
    path: memoryPath(id),
    body: JSON.stringify({value: content}),
  });
}

export async function deleteMemory(
  backend: OmiBackend,
  id: string,
): Promise<LegacyWriteResult<void>> {
  const result = await send(backend, {
    id: 'omi-memory-delete',
    method: 'DELETE',
    path: memoryPath(id),
  });
  // Matches the shipping app: an already-deleted memory is a successful delete.
  if (
    result.ok ||
    (result.failure.kind === 'permanent' && result.failure.reason === 'gone')
  )
    return {ok: true, value: undefined};
  return result;
}

export function setMemoryVisibility(
  backend: OmiBackend,
  id: string,
  visibility: MemoryVisibility,
) {
  return send(backend, {
    id: 'omi-memory-patch',
    method: 'PATCH',
    path: `${memoryPath(id)}/visibility`,
    body: JSON.stringify({value: visibility}),
  });
}
