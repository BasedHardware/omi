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

export function conversationShareUrl(id: string): string {
  const uuidHex = Array.from({length: 32}, () =>
    Math.floor(Math.random() * 16).toString(16),
  ).join('');
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
