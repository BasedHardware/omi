import type {OmiBackend} from './omiNative';

export type ConversationProjection = {
  kind: 'conversation';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  startedAt: string;
  finishedAt: string;
  starred: boolean;
};

export type MemoryProjection = {
  kind: 'memory';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  citations: string[];
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
  sortOrder: number;
  createdAt: number;
  updatedAt: number;
};

export type DesktopReadProjection =
  | ConversationProjection
  | MemoryProjection
  | TaskProjection;

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
): Record<string, unknown>[] {
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
  if ((hasMore && window.nextCursor === null) || (complete && hasMore)) {
    throw new Error(`${label} window is malformed`);
  }
  const completeness = object(page.completeness, `${label} completeness`);
  if (completeness.version !== completenessVersion) {
    throw new Error(`${label} completeness version is malformed`);
  }
  string(completeness.status, `${label} completeness status`);
  if (
    !Array.isArray(completeness.reasons) ||
    !completeness.reasons.every(reason => typeof reason === 'string')
  ) {
    throw new Error(`${label} completeness reasons are malformed`);
  }
  if (page.absence !== null) {
    object(page.absence, `${label} absence`);
  }
  return page.items.map((item, index) =>
    object(item, `${label} item ${index}`),
  );
}

export async function loadConversations(
  backend: OmiBackend,
): Promise<ConversationProjection[]> {
  const value = await read(
    backend,
    'desktop-conversations-read',
    '/v1/conversations?limit=50&offset=0',
  );
  if (!Array.isArray(value)) {
    throw new Error('Conversations response is malformed');
  }
  return value.map((entry, index) => {
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
    const startedAt = string(
      record.started_at,
      `Conversation ${index} started_at`,
    );
    const finishedAt = string(
      record.finished_at,
      `Conversation ${index} finished_at`,
    );
    string(record.created_at, `Conversation ${index} created_at`);
    string(record.updated_at, `Conversation ${index} updated_at`);
    string(record.source, `Conversation ${index} source`);
    string(record.status, `Conversation ${index} status`);
    boolean(record.discarded, `Conversation ${index} discarded`);
    const starred = boolean(record.starred, `Conversation ${index} starred`);
    const visibility = string(
      record.visibility,
      `Conversation ${index} visibility`,
    );
    if (!['public', 'private', 'shared'].includes(visibility)) {
      throw new Error(`Conversation ${index} visibility is malformed`);
    }
    boolean(record.is_locked, `Conversation ${index} is_locked`);
    if (record.folder_id !== null && typeof record.folder_id !== 'string') {
      throw new Error(`Conversation ${index} folder_id is malformed`);
    }
    return {
      kind: 'conversation',
      id,
      title,
      summary,
      searchableText: `${title}\n${summary}`,
      startedAt,
      finishedAt,
      starred,
    };
  });
}

export async function loadMemories(
  backend: OmiBackend,
): Promise<MemoryProjection[]> {
  const items = validatePage(
    await read(backend, 'desktop-memories-read', '/v1/memories?limit=50'),
    'Memories response',
    'recall-completeness-v1',
  );
  return items.map((item, index) => {
    const id = string(item.id, `Memory ${index} id`);
    const text = string(item.text, `Memory ${index} text`);
    const citations = stringArray(item.citations, `Memory ${index} citations`);
    const provenance = object(item.provenance, `Memory ${index} provenance`);
    string(provenance.synthesisVersion, `Memory ${index} synthesisVersion`);
    string(provenance.inputDigest, `Memory ${index} inputDigest`);
    string(provenance.outputDigest, `Memory ${index} outputDigest`);
    return {
      kind: 'memory',
      id,
      title: text,
      summary: text,
      searchableText: text,
      citations,
    };
  });
}

export async function loadTasks(
  backend: OmiBackend,
): Promise<TaskProjection[]> {
  const items = validatePage(
    await read(backend, 'desktop-tasks-read', '/v1/tasks'),
    'Tasks response',
    'tasks-completeness-v1',
  );
  return items.map((item, index) => {
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
    string(item.source, `Task ${index} source`);
    stringArray(item.provenance, `Task ${index} provenance`);
    const sortOrder = finite(item.sortOrder, `Task ${index} sortOrder`);
    const indentLevel = integer(item.indentLevel, `Task ${index} indentLevel`);
    if (indentLevel < 0) {
      throw new Error(`Task ${index} indentLevel is malformed`);
    }
    const createdAt = integer(item.createdAt, `Task ${index} createdAt`);
    const updatedAt = integer(item.updatedAt, `Task ${index} updatedAt`);
    string(item.revision, `Task ${index} revision`);
    return {
      kind: 'task',
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
      sortOrder,
      createdAt,
      updatedAt,
    };
  });
}

export async function loadDesktopReads(
  backend: OmiBackend,
): Promise<DesktopReadProjection[]> {
  const [conversations, memories, tasks] = await Promise.all([
    loadConversations(backend),
    loadMemories(backend),
    loadTasks(backend),
  ]);
  return [...conversations, ...memories, ...tasks];
}
