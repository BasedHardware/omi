import type {NativeHttpResponse, OmiBackend} from './omiNative';

export type ChatMessage = {
  id: string;
  text: string;
  sender: 'human' | 'ai';
  createdAt: number;
  generationOutcome: 'completed' | 'cancelled' | 'failed' | null;
  generationId?: string;
  generationRetryable?: boolean;
  localOnly?: boolean;
};

export type ChatHistoryPage = {
  messages: ChatMessage[];
  olderCursor: string | null;
  hasOlder: boolean;
};
type HistoryEnvelope = {
  messages: ChatMessage[];
  page: {olderCursor: string | null; hasOlder: boolean};
};
type AdmissionEnvelope = {message: ChatMessage; generation: {id: string}};
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

export function chatErrorCopy(error: unknown): string {
  if (!(error instanceof ChatBackendError)) {
    return 'Message not sent. Check your connection and try again.';
  }
  if (error.action === 'reauthenticate' || error.status === 401) {
    return 'Sign in again to continue.';
  }
  if (error.status === 429) {
    return error.retryAfterSeconds === null
      ? 'Too many requests. Try again shortly.'
      : `Too many requests. Try again in ${error.retryAfterSeconds} seconds.`;
  }
  if (error.retryable || error.status === 503) {
    return 'Omi is temporarily unavailable. Try again.';
  }
  return 'This request cannot be completed.';
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

function parseObject(body: string | null): Record<string, unknown> {
  if (body === null) {
    throw new Error('Backend returned an empty response');
  }
  const value: unknown = JSON.parse(body);
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Backend returned an invalid response');
  }
  return value as Record<string, unknown>;
}

export async function loadChatHistory(
  backend: OmiBackend,
): Promise<ChatMessage[]> {
  return (await loadNewestChatHistory(backend)).messages;
}

export async function loadNewestChatHistory(
  backend: OmiBackend,
): Promise<ChatHistoryPage> {
  return loadChatHistoryPage(backend, '/v1/chat-messages?limit=50');
}

export async function loadOlderChatHistory(
  backend: OmiBackend,
  olderCursor: string,
): Promise<ChatHistoryPage> {
  if (olderCursor.length === 0) {
    throw new Error('Chat history cursor is empty');
  }
  return loadChatHistoryPage(
    backend,
    `/v1/chat-messages?limit=50&olderCursor=${encodeURIComponent(olderCursor)}`,
  );
}

async function loadChatHistoryPage(
  backend: OmiBackend,
  path: `/v1/chat-messages?${string}`,
): Promise<ChatHistoryPage> {
  const response = await backend.request({
    id: 'chat-history',
    method: 'GET',
    path,
  });
  if (response.status !== 200) {
    throwBackendError(response);
  }
  const envelope = parseObject(response.body) as HistoryEnvelope;
  if (
    !Array.isArray(envelope.messages) ||
    envelope.page === undefined ||
    typeof envelope.page.hasOlder !== 'boolean' ||
    !(
      envelope.page.olderCursor === null ||
      typeof envelope.page.olderCursor === 'string'
    ) ||
    envelope.page.hasOlder !== (envelope.page.olderCursor !== null)
  ) {
    throw new Error('Chat history is malformed');
  }
  return {
    messages: envelope.messages,
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
): Promise<{human: ChatMessage; assistant: ChatMessage | null}> {
  const id = (localMessage ?? createLocalChatMessage(text, now)).id;
  const response = await backend.request({
    id: `admit-${id}`,
    method: 'POST',
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
  const admission = parseObject(response.body) as AdmissionEnvelope;
  if (typeof admission.generation?.id !== 'string') {
    throw new Error('Chat admission is malformed');
  }
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
  const humanIndex = history.findIndex(
    message => message.id === admission.message.id,
  );
  const assistant = history
    .slice(humanIndex + 1)
    .find(message => message.sender === 'ai');
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
  throw new ChatBackendError(
    response.status,
    code,
    retryable,
    action,
    response.retryAfterSeconds ?? null,
  );
}

export function parseTerminal(raw: string): TerminalFrame {
  const blocks = raw.split(/\r?\n\r?\n/).filter(Boolean);
  for (let index = blocks.length - 1; index >= 0; index -= 1) {
    const data = blocks[index]
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n');
    if (data === '') {
      continue;
    }
    const frame = JSON.parse(data) as {kind?: string};
    if (
      frame.kind === 'done' ||
      frame.kind === 'cancelled' ||
      frame.kind === 'failed'
    ) {
      return frame as TerminalFrame;
    }
  }
  throw new Error('Generation ended without a terminal frame');
}
