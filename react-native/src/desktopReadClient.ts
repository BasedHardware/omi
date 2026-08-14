import type {OmiBackend} from './omiNative';

export type ConversationProjection = {
  kind: 'conversation';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  starred: boolean;
  status: string;
  locked: boolean;
  discarded: boolean;
};

export type MemoryProjection = {
  kind: 'memory';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  citations: string[];
  timestamp: number | null;
  provenance: {
    label: string | null;
    synthesisVersion: string;
    inputDigest: string;
    outputDigest: string;
  };
};

export type TaskProjection = {
  kind: 'task';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  completed: boolean;
  completedAt: number | null;
  dueAt: number | null;
  owner: string | null;
  source: string;
  provenance: string[];
  sortOrder: number;
  indentLevel: number;
  createdAt: number;
  updatedAt: number;
  revision: string | null;
};

export type TaskGroup = 'Today' | 'Tomorrow' | 'Later';

export function taskGroup(
  dueAt: number | null,
  nowEpochSeconds: number,
): TaskGroup {
  if (dueAt === null) {
    return 'Later';
  }
  const today = Math.floor(nowEpochSeconds / 86400);
  const dueDay = Math.floor(dueAt / 86400);
  if (dueDay <= today) {
    return 'Today';
  }
  return dueDay === today + 1 ? 'Tomorrow' : 'Later';
}

export type DesktopReadProjection =
  | ConversationProjection
  | MemoryProjection
  | TaskProjection;

export type ReadPageState = {
  windowStatus: 'complete' | 'more' | 'incomplete' | 'unknown';
  complete: boolean;
  hasMore: boolean;
  nextCursor: string | null;
  completenessStatus: 'complete' | 'incomplete' | 'degraded' | 'unknown';
  reasons: string[];
};

export type DomainRead<T extends DesktopReadProjection> = {
  items: T[];
  page: ReadPageState;
};

export type TaskRead = DomainRead<TaskProjection> & {
  accountEpoch: number | null;
};

export type DomainReadOutcome<T extends DesktopReadProjection> =
  | {status: 'success'; value: DomainRead<T>}
  | {status: 'error'; error: string};

export type DesktopReadOutcomes = {
  conversations: DomainReadOutcome<ConversationProjection>;
  memories: DomainReadOutcome<MemoryProjection>;
  tasks: DomainReadOutcome<TaskProjection>;
};

function object(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} is malformed`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${label} is malformed`);
  }
  return value;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') {
    throw new Error(`${label} is malformed`);
  }
  return value;
}

function finite(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} is malformed`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  const result = finite(value, label);
  if (!Number.isSafeInteger(result)) {
    throw new Error(`${label} is malformed`);
  }
  return result;
}

function nullableInteger(value: unknown, label: string): number | null {
  return value === null ? null : integer(value, label);
}

function timestamp(value: unknown, label: string): string {
  const result = string(value, label);
  if (!Number.isFinite(Date.parse(result))) {
    throw new Error(`${label} is malformed`);
  }
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value === null ? null : timestamp(value, label);
}

function optionalTimestamp(
  record: Record<string, unknown>,
  label: string,
): number | null {
  const value = record.updatedAt ?? record.createdAt;
  return value === undefined ? null : integer(value, label);
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every(item => typeof item === 'string')) {
    throw new Error(`${label} is malformed`);
  }
  return [...value];
}

function parseJson(body: string | null, label: string): unknown {
  if (body === null) {
    throw new Error(`${label} returned an empty response`);
  }
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw new Error(`${label} returned invalid JSON`);
  }
}

async function read(
  backend: OmiBackend,
  id: string,
  path: `/${string}`,
): Promise<unknown> {
  const response = await backend.request({id, method: 'GET', path});
  if (response.status !== 200) {
    throw new Error(`${id} failed (${response.status})`);
  }
  return parseJson(response.body, id);
}

function validatePage(
  value: unknown,
  label: string,
  completenessVersion: 'recall-completeness-v1' | 'tasks-completeness-v1',
): {items: Record<string, unknown>[]; page: ReadPageState} {
  const page = object(value, label);
  if (page.contractVersion !== '1.0.0') {
    throw new Error(`${label} contractVersion is malformed`);
  }
  if (!Array.isArray(page.items)) {
    throw new Error(`${label} items are malformed`);
  }
  const window = object(page.window, `${label} window`);
  const windowStatus = string(window.status, `${label} window status`);
  if (!['complete', 'more', 'incomplete'].includes(windowStatus)) {
    throw new Error(`${label} window status is malformed`);
  }
  const complete = boolean(window.complete, `${label} window complete`);
  const hasMore = boolean(window.hasMore, `${label} window hasMore`);
  if (window.nextCursor !== null && typeof window.nextCursor !== 'string') {
    throw new Error(`${label} window cursor is malformed`);
  }
  if (
    (hasMore &&
      (window.nextCursor === null || window.nextCursor.length === 0)) ||
    (complete && hasMore)
  ) {
    throw new Error(`${label} window is malformed`);
  }
  const completeness = object(page.completeness, `${label} completeness`);
  if (completeness.version !== completenessVersion) {
    throw new Error(`${label} completeness version is malformed`);
  }
  const completenessStatus = string(
    completeness.status,
    `${label} completeness status`,
  );
  if (!['complete', 'incomplete', 'degraded'].includes(completenessStatus)) {
    throw new Error(`${label} completeness status is malformed`);
  }
  if (
    !Array.isArray(completeness.reasons) ||
    !completeness.reasons.every(reason => typeof reason === 'string')
  ) {
    throw new Error(`${label} completeness reasons are malformed`);
  }
  if (page.absence !== null) {
    object(page.absence, `${label} absence`);
  }
  return {
    items: page.items.map((item, index) =>
      object(item, `${label} item ${index}`),
    ),
    page: {
      windowStatus: windowStatus as ReadPageState['windowStatus'],
      complete,
      hasMore,
      nextCursor: window.nextCursor as string | null,
      completenessStatus:
        completenessStatus as ReadPageState['completenessStatus'],
      reasons: [...completeness.reasons] as string[],
    },
  };
}

export async function loadConversations(
  backend: OmiBackend,
): Promise<DomainRead<ConversationProjection>> {
  const value = await read(
    backend,
    'desktop-conversations-read',
    '/v1/conversations?limit=50&offset=0',
  );
  if (!Array.isArray(value)) {
    throw new Error('Conversations response is malformed');
  }
  const items = value.map((entry, index) => {
    const record = object(entry, `Conversation ${index}`);
    const structured = object(
      record.structured,
      `Conversation ${index} structured`,
    );
    const id = string(record.id, `Conversation ${index} id`);
    const title = string(structured.title, `Conversation ${index} title`);
    const summary = string(
      structured.overview,
      `Conversation ${index} overview`,
    );
    const createdAt = timestamp(
      record.created_at,
      `Conversation ${index} created_at`,
    );
    const updatedAt = timestamp(
      record.updated_at,
      `Conversation ${index} updated_at`,
    );
    const startedAt = nullableTimestamp(
      record.started_at,
      `Conversation ${index} started_at`,
    );
    const finishedAt = nullableTimestamp(
      record.finished_at,
      `Conversation ${index} finished_at`,
    );
    string(record.source, `Conversation ${index} source`);
    const status = string(record.status, `Conversation ${index} status`);
    const discarded = boolean(
      record.discarded,
      `Conversation ${index} discarded`,
    );
    const starred = boolean(record.starred, `Conversation ${index} starred`);
    const visibility = string(
      record.visibility,
      `Conversation ${index} visibility`,
    );
    if (!['public', 'private', 'shared'].includes(visibility)) {
      throw new Error(`Conversation ${index} visibility is malformed`);
    }
    const locked = boolean(record.is_locked, `Conversation ${index} is_locked`);
    if (record.folder_id !== null && typeof record.folder_id !== 'string') {
      throw new Error(`Conversation ${index} folder_id is malformed`);
    }
    return {
      kind: 'conversation' as const,
      id,
      title,
      summary,
      searchableText: `${title}\n${summary}`,
      createdAt,
      updatedAt,
      startedAt,
      finishedAt,
      starred,
      status,
      locked,
      discarded,
    };
  });
  const hasMore = items.length === 50;
  return {
    items,
    page: {
      windowStatus: hasMore ? 'unknown' : 'complete',
      complete: !hasMore,
      hasMore,
      nextCursor: null,
      completenessStatus: hasMore ? 'unknown' : 'complete',
      reasons: hasMore ? ['limit_reached'] : [],
    },
  };
}

export function parseMemoryText(text: string): {
  body: string;
  provenanceLabel: string | null;
} {
  const match =
    text.match(/^((?:[a-z0-9_-]+:){2,}[a-z0-9_-]+)\s+(.+)$/is) ??
    text.match(/^([a-z0-9]+(?:-[a-z0-9]+){2,}):\s+(.+)$/is);
  return match === null
    ? {body: text, provenanceLabel: null}
    : {body: match[2], provenanceLabel: match[1]};
}

export async function loadMemories(
  backend: OmiBackend,
  cursor: string | null = null,
): Promise<DomainRead<MemoryProjection>> {
  if (cursor !== null && cursor.length === 0) {
    throw new Error('Memory cursor is malformed');
  }
  const path: `/${string}` =
    cursor === null
      ? '/v1/memories?limit=50'
      : `/v1/memories?limit=50&cursor=${encodeURIComponent(cursor)}`;
  const validated = validatePage(
    await read(backend, 'desktop-memories-read', path),
    'Memories response',
    'recall-completeness-v1',
  );
  const items = validated.items.map((item, index) => {
    const id = string(item.id, `Memory ${index} id`);
    const text = string(item.text, `Memory ${index} text`);
    const parsedText = parseMemoryText(text);
    const citations = stringArray(item.citations, `Memory ${index} citations`);
    const provenance = object(item.provenance, `Memory ${index} provenance`);
    const synthesisVersion = string(
      provenance.synthesisVersion,
      `Memory ${index} synthesisVersion`,
    );
    const inputDigest = string(
      provenance.inputDigest,
      `Memory ${index} inputDigest`,
    );
    const outputDigest = string(
      provenance.outputDigest,
      `Memory ${index} outputDigest`,
    );
    return {
      kind: 'memory' as const,
      id,
      title: parsedText.body,
      summary: parsedText.body,
      searchableText: `${parsedText.body}\n${citations.join('\n')}`,
      citations,
      timestamp: optionalTimestamp(item, `Memory ${index} timestamp`),
      provenance: {
        label: parsedText.provenanceLabel,
        synthesisVersion,
        inputDigest,
        outputDigest,
      },
    };
  });
  return {items, page: validated.page};
}

export async function loadTasks(backend: OmiBackend): Promise<TaskRead> {
  const value = await read(backend, 'desktop-tasks-read', '/v1/tasks');
  const accountEpochValue = object(value, 'Tasks response').accountEpoch;
  const accountEpoch =
    accountEpochValue === undefined
      ? null
      : integer(accountEpochValue, 'Tasks response accountEpoch');
  const validated = validatePage(
    value,
    'Tasks response',
    'tasks-completeness-v1',
  );
  const items = validated.items.map((item, index) => {
    const id = string(item.id, `Task ${index} id`);
    const description = string(item.description, `Task ${index} description`);
    const completed = boolean(item.completed, `Task ${index} completed`);
    const completedAt = nullableInteger(
      item.completedAt,
      `Task ${index} completedAt`,
    );
    const dueAt = nullableInteger(item.dueAt, `Task ${index} dueAt`);
    if (item.owner !== null && typeof item.owner !== 'string') {
      throw new Error(`Task ${index} owner is malformed`);
    }
    const owner = item.owner as string | null;
    const source = string(item.source, `Task ${index} source`);
    const provenance = stringArray(item.provenance, `Task ${index} provenance`);
    const sortOrder = finite(item.sortOrder, `Task ${index} sortOrder`);
    const indentLevel = integer(item.indentLevel, `Task ${index} indentLevel`);
    if (indentLevel < 0) {
      throw new Error(`Task ${index} indentLevel is malformed`);
    }
    const createdAt = integer(item.createdAt, `Task ${index} createdAt`);
    const updatedAt = integer(item.updatedAt, `Task ${index} updatedAt`);
    const revision =
      item.revision === null
        ? null
        : string(item.revision, `Task ${index} revision`);
    return {
      kind: 'task' as const,
      id,
      title: description,
      summary: completed
        ? 'Completed'
        : dueAt === null
        ? 'Pending'
        : `Due ${dueAt}`,
      searchableText: description,
      completed,
      completedAt,
      dueAt,
      owner,
      source,
      provenance,
      sortOrder,
      indentLevel,
      createdAt,
      updatedAt,
      revision,
    };
  });
  return {items, page: validated.page, accountEpoch};
}

export async function loadDesktopReads(
  backend: OmiBackend,
): Promise<DesktopReadOutcomes> {
  const [conversations, memories, tasks] = await Promise.allSettled([
    loadConversations(backend),
    loadMemories(backend),
    loadTasks(backend),
  ]);
  const outcome = <T extends DesktopReadProjection>(
    result: PromiseSettledResult<DomainRead<T>>,
  ): DomainReadOutcome<T> =>
    result.status === 'fulfilled'
      ? {status: 'success', value: result.value}
      : {
          status: 'error',
          error:
            result.reason instanceof Error
              ? result.reason.message
              : 'Desktop read failed',
        };
  return {
    conversations: outcome(conversations),
    memories: outcome(memories),
    tasks: outcome(tasks),
  };
}
