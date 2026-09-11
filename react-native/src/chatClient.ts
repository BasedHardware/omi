import {attachOmiChatAppNames} from './legacyOmiApps';
import {
  omiHistoryOffset,
  parseOmiHistory,
  parseOmiChatStream,
} from './legacyOmiChat';
import type {NativeHttpResponse, OmiBackend} from './omiNative';
import {
  parseChatGenerationEventStream,
  wireToChatAdmissionEnvelope,
  wireToChatHistoryEnvelope,
} from '@omi-core/adapters-platform/dist/chat';

export type ChatMessageAttachment = {
  id: string;
  displayName: string;
  mediaType: string;
  sizeBytes?: number;
  thumbnail?: string;
};

export type ChatMessage = {
  id: string;
  text: string;
  sender: 'human' | 'ai' | 'unknown';
  type?: 'text' | 'day_summary' | 'unknown';
  createdAt: number;
  generationOutcome: 'completed' | 'cancelled' | 'failed' | null;
  generationId?: string;
  generationRetryable?: boolean;
  localOnly?: boolean;
  attachments?: ChatMessageAttachment[];
  memories?: {title: string; emoji?: string}[];
  chart?: {
    title: string;
    points: {label: string; value: number}[];
  };
  evidence?: {title: string; detail: string}[];
  contentBlocks?: {eyebrow: string; title?: string; detail?: string}[];
  appId?: string;
  appName?: string;
};

export type ChatHistoryPage = {
  messages: ChatMessage[];
  olderCursor: string | null;
  hasOlder: boolean;
};
type ParsedChatMessage = NonNullable<
  ReturnType<typeof wireToChatHistoryEnvelope>
>['messages'][number];
type AdmissionEnvelope = {
  message: ChatMessage;
  generation: {id: string};
};
type TerminalFrame =
  | {kind: 'done'; message: ChatMessage}
  | {kind: 'cancelled'; message: ChatMessage | null}
  | {kind: 'failed'; error: {code: string; retryable: boolean}};

export class ChatBackendError extends Error {
  constructor(
    readonly status: number,
    readonly backendCode: string,
    readonly retryable: boolean,
    readonly action: string,
    readonly retryAfterSeconds: number | null,
  ) {
    super(`Chat backend failed (${status}:${backendCode})`);
  }
}

export function chatWriteDoorUnavailable(error: unknown): boolean {
  if (nativeErrorCode(error) === 'OMI_DEV_BACKEND_UNSUPPORTED') {
    return true;
  }
  return (
    error instanceof ChatBackendError &&
    (error.backendCode === 'development_backend_unsupported' ||
      ((error.status === 404 || error.backendCode === 'not_found') &&
        error.action !== 'edit_request'))
  );
}

export function chatHistoryHasOlder(
  hasOlder: boolean,
  olderCursor: string | null,
): boolean {
  return hasOlder && olderCursor !== null && olderCursor.length > 0;
}

export function chatComposerIsResting(
  messageCount: number,
  chatBusy: boolean,
  olderAvailable: boolean,
  chatError: string | null,
  historySettled: boolean,
): boolean {
  return (
    historySettled &&
    messageCount === 0 &&
    !chatBusy &&
    !olderAvailable &&
    chatError === null
  );
}

export function chatErrorCopy(error: unknown): string {
  if (chatWriteDoorUnavailable(error)) {
    return 'Sending messages is not available on this backend yet.';
  }
  if (!(error instanceof ChatBackendError)) {
    return 'Message not sent. Check your connection and try again.';
  }
  if (error.action === 'reauthenticate' || error.status === 401) {
    return 'Sign in again to continue.';
  }
  if (error.status === 403 || error.backendCode === 'forbidden') {
    return 'Chat is not available for this account.';
  }
  if (error.status === 429) {
    return error.retryAfterSeconds === null
      ? 'Too many requests. Try again shortly.'
      : `Too many requests. Try again in ${error.retryAfterSeconds} seconds.`;
  }
  if (error.retryable) {
    return 'Omi is temporarily unavailable. Try again.';
  }
  return 'This request cannot be completed.';
}

function nativeErrorCode(value: unknown): string | null {
  if (value === null || typeof value !== 'object') {
    return null;
  }
  const code = (value as {code?: unknown}).code;
  return typeof code === 'string' ? code : null;
}

// A chat failure that means "this client no longer holds a usable cloud
// session": a backend 401 / reauthenticate action, or native credentials that
// never resolved. Callers use it to re-probe the session instead of keeping a
// signed-in shell up with a dead Bearer.
export function chatSessionLost(error: unknown): boolean {
  if (error instanceof ChatBackendError) {
    return error.status === 401 || error.action === 'reauthenticate';
  }
  const code =
    error !== null && typeof error === 'object'
      ? (error as {code?: unknown}).code
      : null;
  return (
    code === 'OMI_HTTP_UNCONFIGURED' ||
    code === 'OMI_HTTP_UNAUTHORIZED' ||
    (error instanceof Error &&
      error.message === 'Native HTTP configuration is unavailable')
  );
}

export function chatHistoryErrorCopy(error: unknown): string {
  if (chatWriteDoorUnavailable(error)) {
    return 'Chat history is not available on this backend yet.';
  }
  if (error instanceof ChatBackendError) {
    return chatErrorCopy(error);
  }
  const code = nativeErrorCode(error);
  if (
    code === 'OMI_HTTP_UNCONFIGURED' ||
    code === 'OMI_HTTP_UNAUTHORIZED' ||
    code === 'unauthorized' ||
    (error instanceof Error &&
      error.message === 'Native HTTP configuration is unavailable')
  ) {
    return 'Sign in again to continue.';
  }
  if (
    code === 'OMI_HTTP_TRANSPORT' ||
    (error instanceof Error && error.message === 'Native HTTP transport failed')
  ) {
    return 'Omi is temporarily unavailable. Try again.';
  }
  return 'Chat history could not be loaded. Check your connection and try again.';
}

export function chatHistoryCanReload(error: unknown): boolean {
  if (chatWriteDoorUnavailable(error)) {
    return false;
  }
  if (!(error instanceof ChatBackendError)) {
    return true;
  }
  if (error.status === 403 || error.backendCode === 'forbidden') {
    return true;
  }
  return error.retryable;
}

export function chatHistoryShouldRefresh(error: unknown): boolean {
  return (
    error instanceof ChatBackendError &&
    error.action === 'refresh_history' &&
    (error.status === 410 || error.status === 400)
  );
}

export function chatCancelErrorCopy(error: unknown): string {
  if (chatWriteDoorUnavailable(error)) {
    return 'Stopping the response is not available on this backend yet.';
  }
  return 'Could not stop the response.';
}

let messageSequence = 0;

export function createLocalChatMessage(
  text: string,
  now: number = Date.now(),
): ChatMessage {
  messageSequence += 1;
  return {
    id: `desktop-${now}-${messageSequence}`,
    text,
    sender: 'human',
    createdAt: now,
    generationOutcome: null,
    localOnly: true,
  };
}

function parseJson(body: string | null): unknown {
  if (body === null) {
    throw new Error('Backend returned an empty response');
  }
  return JSON.parse(body) as unknown;
}

function desktopChatMessage(message: ParsedChatMessage): ChatMessage {
  if (
    message.sender !== 'human' &&
    message.sender !== 'ai' &&
    message.sender !== 'unknown'
  ) {
    throw new Error('Chat message sender is unsupported');
  }
  return {
    id: message.id,
    text: message.text,
    sender: message.sender,
    createdAt: message.createdAt,
    generationOutcome: message.generationOutcome,
    ...(message.type === 'day_summary' ? {type: 'day_summary' as const} : {}),
    ...(message.attachments.length > 0
      ? {
          attachments: message.attachments.map(attachment => ({
            id: attachment.id,
            displayName: attachment.displayName,
            mediaType: attachment.mediaType,
            sizeBytes: attachment.sizeBytes,
          })),
        }
      : {}),
  };
}

export async function loadChatHistory(
  backend: OmiBackend,
): Promise<ChatMessage[]> {
  return (await loadNewestChatHistory(backend)).messages;
}

export async function loadNewestChatHistory(
  backend: OmiBackend,
  chatSessionId?: string,
): Promise<ChatHistoryPage> {
  if ((await backend.getApiContract?.()) === 'omi') {
    if (chatSessionId !== undefined) {
      throw new ChatBackendError(404, 'not_found', false, 'none', null);
    }
    return loadOmiHistory(backend, 0);
  }
  return loadChatHistoryPage(
    backend,
    canonicalChatHistoryPath({chatSessionId}),
  );
}

export async function loadOlderChatHistory(
  backend: OmiBackend,
  olderCursor: string,
  chatSessionId?: string,
): Promise<ChatHistoryPage> {
  if ((await backend.getApiContract?.()) === 'omi') {
    if (chatSessionId !== undefined) {
      throw new ChatBackendError(404, 'not_found', false, 'none', null);
    }
    return loadOmiHistory(backend, omiHistoryOffset(olderCursor));
  }
  if (olderCursor.length === 0) {
    throw new Error('Chat history cursor is empty');
  }
  return loadChatHistoryPage(
    backend,
    canonicalChatHistoryPath({olderCursor, chatSessionId}),
  );
}

function canonicalChatHistoryPath(query: {
  olderCursor?: string;
  chatSessionId?: string;
}): string {
  let path = '/v1/chat-messages?limit=50';
  if (query.olderCursor !== undefined) {
    path += `&olderCursor=${encodeURIComponent(query.olderCursor)}`;
  }
  if (query.chatSessionId !== undefined) {
    path += `&chatSessionId=${encodeURIComponent(query.chatSessionId)}`;
  }
  return path;
}

async function loadOmiHistory(
  backend: OmiBackend,
  offset: number,
): Promise<ChatHistoryPage> {
  const response = await backend.request({
    id: 'omi-chat-history',
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v2/messages?limit=50&offset=${offset}`,
  });
  if (response.status !== 200) throwBackendError(response);
  const page = parseOmiHistory(response.body, offset);
  return {
    ...page,
    messages: await attachOmiChatAppNames(backend, page.messages),
  };
}

async function loadChatHistoryPage(
  backend: OmiBackend,
  path: `/v1/chat-messages?${string}`,
): Promise<ChatHistoryPage> {
  const response = await backend.request({
    id: 'chat-history',
    method: 'GET',
    expectedApiContract: 'canonical',
    path,
  });
  if (response.status !== 200) {
    throwBackendError(response);
  }
  const envelope = wireToChatHistoryEnvelope(parseJson(response.body));
  if (envelope === null) {
    throw new Error('Chat history is malformed');
  }
  return {
    messages: envelope.messages.map(desktopChatMessage),
    olderCursor: envelope.page.olderCursor,
    hasOlder: envelope.page.hasOlder,
  };
}

export function mergeOlderChatHistory(
  current: ChatMessage[],
  older: ChatMessage[],
): ChatMessage[] {
  const currentIds = new Set(current.map(message => message.id));
  return [...older.filter(message => !currentIds.has(message.id)), ...current];
}

export function reconcileCanonicalChatHistory(
  local: ChatMessage[],
  canonical: ChatMessage[],
): ChatMessage[] {
  const canonicalIds = new Set(canonical.map(message => message.id));
  return [
    ...canonical,
    ...local.filter(message => !canonicalIds.has(message.id)),
  ];
}

export async function sendChatMessage(
  backend: OmiBackend,
  text: string,
  now: number = Date.now(),
  onGenerationStarted?: (generationId: string) => void,
  localMessage?: ChatMessage,
  onRequestStarted?: (requestId: string) => boolean | void,
): Promise<{human: ChatMessage; assistant: ChatMessage | null}> {
  if ((await backend.getApiContract?.()) === 'omi') {
    if (backend.sendOmiChat === undefined)
      throw new Error('Omi chat transport is unavailable');
    const human = localMessage ?? createLocalChatMessage(text, now);
    if (onRequestStarted?.(human.id) === false) {
      throw Object.assign(new Error('Omi chat request retired'), {
        code: 'OMI_HTTP_CANCELLED',
      });
    }
    const response = await backend.sendOmiChat(human.id, text);
    if (response.status !== 200) throwBackendError(response);
    const assistant = parseOmiChatStream(response.body);
    const [named] = await attachOmiChatAppNames(backend, [assistant]);
    return {human, assistant: named};
  }
  const id = (localMessage ?? createLocalChatMessage(text, now)).id;
  const response = await backend.request({
    id: `admit-${id}`,
    method: 'POST',
    expectedApiContract: 'canonical',
    path: '/v1/chat-messages',
    body: JSON.stringify({
      op: 'create',
      opId: `op-${id}`,
      id,
      at: now,
      text,
      sender: 'human',
      journalRevision: 1,
      type: 'text',
      appId: null,
      chatSessionId: null,
      messageSource: 'desktop_chat',
      metadata: null,
      attachmentIds: [],
    }),
  });
  if (response.status !== 200 && response.status !== 201) {
    throwBackendError(response);
  }
  const wireAdmission = wireToChatAdmissionEnvelope(parseJson(response.body));
  if (wireAdmission === null) {
    throw new Error('Chat admission is malformed');
  }
  const admission: AdmissionEnvelope = {
    message: desktopChatMessage(wireAdmission.message),
    generation: wireAdmission.generation,
  };
  onGenerationStarted?.(admission.generation.id);
  let terminal: TerminalFrame;
  try {
    terminal = parseTerminal(
      readGeneration(
        await backend.generationEvents(admission.generation.id, null),
      ),
    );
  } catch (error) {
    if (isNativeCancellation(error)) {
      try {
        terminal = parseTerminal(
          readGeneration(
            await backend.generationEvents(admission.generation.id, null),
          ),
        );
      } catch (replayError) {
        if (!isReplayExpired(replayError)) {
          throw replayError;
        }
        return reconcileGeneration(admission, await loadChatHistory(backend));
      }
    } else {
      if (!isReplayExpired(error)) {
        throw error;
      }
      return reconcileGeneration(admission, await loadChatHistory(backend));
    }
  }
  if (terminal.kind === 'failed') {
    return {
      human: admission.message,
      assistant: {
        id: `generation:${admission.generation.id}`,
        text: '',
        sender: 'ai',
        createdAt: admission.message.createdAt,
        generationOutcome: 'failed',
        generationId: admission.generation.id,
        generationRetryable: terminal.error.retryable,
        localOnly: true,
      },
    };
  }
  if (terminal.kind === 'cancelled' && terminal.message === null) {
    return {
      human: admission.message,
      assistant: {
        id: `generation:${admission.generation.id}`,
        text: '',
        sender: 'ai',
        createdAt: admission.message.createdAt,
        generationOutcome: 'cancelled',
        generationId: admission.generation.id,
        localOnly: true,
      },
    };
  }
  return {human: admission.message, assistant: terminal.message};
}

function reconcileGeneration(
  admission: AdmissionEnvelope,
  history: ChatMessage[],
): {human: ChatMessage; assistant: ChatMessage} {
  const canonicalHuman = history.find(
    message => message.id === admission.message.id,
  );
  const assistant = history.find(
    message =>
      message.id === admission.generation.id && message.sender === 'ai',
  );
  if (canonicalHuman === undefined || assistant === undefined) {
    throw new Error(
      'Generation replay expired before canonical history reconciled',
    );
  }
  return {human: canonicalHuman, assistant};
}

function isNativeCancellation(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === 'object' &&
    'code' in error &&
    error.code === 'OMI_HTTP_CANCELLED'
  );
}

export async function cancelChatGeneration(
  backend: OmiBackend,
  generationId: string,
): Promise<void> {
  await backend.cancelGenerationEvents(generationId);
}

function isReplayExpired(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === 'object' &&
    ((error instanceof ChatBackendError && error.status === 410) ||
      ('code' in error && error.code === 'OMI_HTTP_REPLAY_EXPIRED'))
  );
}

function readGeneration(response: NativeHttpResponse): string {
  if (response.status !== 200) {
    throwBackendError(response);
  }
  if (response.body === null) {
    throw new Error('Generation returned an empty stream');
  }
  return response.body;
}

function throwBackendError(response: NativeHttpResponse): never {
  let code = 'unknown';
  let retryable = response.status === 503;
  let action = 'none';
  if (response.body !== null) {
    try {
      const parsed = JSON.parse(response.body) as {
        error?:
          | {code?: unknown; retryable?: unknown; action?: unknown}
          | string;
      };
      if (typeof parsed.error === 'string') {
        code = parsed.error;
      } else if (parsed.error !== null && typeof parsed.error === 'object') {
        if (typeof parsed.error.code === 'string') {
          code = parsed.error.code;
        }
        if (typeof parsed.error.retryable === 'boolean') {
          retryable = parsed.error.retryable;
        }
        if (typeof parsed.error.action === 'string') {
          action = parsed.error.action;
        }
      }
    } catch {}
  }
  throw new ChatBackendError(
    response.status,
    code,
    retryable,
    action,
    response.retryAfterSeconds ?? null,
  );
}

export function parseTerminal(raw: string): TerminalFrame {
  const frames = parseChatGenerationEventStream(raw);
  if (frames === null) {
    throw new Error('Generation stream is malformed');
  }
  for (let index = frames.length - 1; index >= 0; index -= 1) {
    const frame = frames[index];
    if (frame.kind === 'done') {
      return {kind: 'done', message: desktopChatMessage(frame.message)};
    }
    if (frame.kind === 'cancelled') {
      return {
        kind: 'cancelled',
        message:
          frame.message === null ? null : desktopChatMessage(frame.message),
      };
    }
    if (frame.kind === 'failed') {
      return {kind: 'failed', error: frame.error};
    }
  }
  throw new Error('Generation ended without a terminal frame');
}
