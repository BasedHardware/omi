import type {OmiBackend} from './omiNative';

export type ChatMessage = {
  id: string;
  text: string;
  sender: 'human' | 'ai';
  createdAt: number;
  generationOutcome: 'completed' | 'cancelled' | null;
};

type HistoryEnvelope = {messages: ChatMessage[]};
type AdmissionEnvelope = {message: ChatMessage; generation: {id: string}};
type TerminalFrame =
  | {kind: 'done'; message: ChatMessage}
  | {kind: 'cancelled'; message: ChatMessage | null}
  | {kind: 'failed'; error: {code: string; retryable: boolean}};

let messageSequence = 0;

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
  const response = await backend.request({
    id: 'chat-history',
    method: 'GET',
    path: '/v1/chat-messages?limit=50',
  });
  if (response.status !== 200) {
    throw new Error(`Chat history failed (${response.status})`);
  }
  const envelope = parseObject(response.body) as HistoryEnvelope;
  if (!Array.isArray(envelope.messages)) {
    throw new Error('Chat history is malformed');
  }
  return envelope.messages;
}

export async function sendChatMessage(
  backend: OmiBackend,
  text: string,
  now: number = Date.now(),
  onGenerationStarted?: (generationId: string) => void,
): Promise<{human: ChatMessage; assistant: ChatMessage | null}> {
  messageSequence += 1;
  const id = `desktop-${now}-${messageSequence}`;
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
    throw new Error(`Chat send failed (${response.status})`);
  }
  const admission = parseObject(response.body) as AdmissionEnvelope;
  if (typeof admission.generation?.id !== 'string') {
    throw new Error('Chat admission is malformed');
  }
  onGenerationStarted?.(admission.generation.id);
  let terminal: TerminalFrame;
  try {
    terminal = parseTerminal(
      await backend.generationEvents(admission.generation.id, null),
    );
  } catch (error) {
    if (!isReplayExpired(error)) {
      throw error;
    }
    const history = await loadChatHistory(backend);
    const canonicalHuman = history.find(
      message => message.id === admission.message.id,
    );
    const assistant = history
      .filter(
        message =>
          message.sender === 'ai' &&
          message.createdAt >= admission.message.createdAt,
      )
      .sort((left, right) => left.createdAt - right.createdAt)[0];
    if (canonicalHuman === undefined || assistant === undefined) {
      throw new Error(
        'Generation replay expired before canonical history reconciled',
      );
    }
    return {human: canonicalHuman, assistant};
  }
  if (terminal.kind === 'failed') {
    throw new Error(`Generation failed (${terminal.error.code})`);
  }
  return {human: admission.message, assistant: terminal.message};
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
    'code' in error &&
    error.code === 'OMI_HTTP_REPLAY_EXPIRED'
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
