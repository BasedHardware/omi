import {
  loadOmiConversations,
  loadOmiMemories,
  loadOmiTasks,
} from './legacyOmiReads';
import {isOptionalCaptureTimestamp} from './captureTimestamp';
import type {OmiBackend} from './omiNative';

export type ConversationProjection = {
  capturedAtMs?: number;
  kind: 'conversation';
  id: string;
  title: string;
  summary: string;
  searchableText: string;
  createdAt: string;
  updatedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  starred: boolean;
  status: string;
  source: string;
  visibility: 'public' | 'private' | 'shared';
  folderId: string | null;
  locked: boolean;
  discarded: boolean;
};

export function conversationGroupLabel(
  value: string,
  nowEpochMilliseconds: number,
): string {
  const date = new Date(value);
  const now = new Date(nowEpochMilliseconds);
  const localDay = (item: Date) =>
    Date.UTC(item.getFullYear(), item.getMonth(), item.getDate()) / 86400000;
  const difference = localDay(now) - localDay(date);
  if (difference === 0) {
    return 'Today';
  }
  if (difference === 1) {
    return 'Yesterday';
  }
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

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
    synthesisVersion: string | null;
    inputDigest: string | null;
    outputDigest: string | null;
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
  createdAt: number | null;
  updatedAt: number | null;
  revision: string | null;
};

export type TaskGroup = 'Today' | 'Tomorrow' | 'Later';

export function taskGroup(
  dueAt: number | null,
  nowMilliseconds: number,
): TaskGroup {
  if (dueAt === null) {
    return 'Later';
  }
  const today = Math.floor(nowMilliseconds / 86400000);
  const dueDay = Math.floor(dueAt / 86400000);
  if (dueDay <= today) {
    return 'Today';
  }
  return dueDay === today + 1 ? 'Tomorrow' : 'Later';
}

export type DesktopReadProjection =
  | ConversationProjection
  | MemoryProjection
  | TaskProjection;

export type TimelineGroup = {
  label: string;
  items: DesktopReadProjection[];
};

export function projectionTimestamp(
  item: DesktopReadProjection,
): number | null {
  const timestamp =
    item.kind === 'conversation'
      ? Date.parse(item.startedAt ?? item.createdAt)
      : item.kind === 'memory'
      ? item.timestamp === null
        ? null
        : item.timestamp * 1000
      : item.createdAt;
  return timestamp === null || !Number.isFinite(timestamp) ? null : timestamp;
}

export function timelineGroups(
  items: DesktopReadProjection[],
  nowEpochMilliseconds: number,
): TimelineGroup[] {
  const groups = new Map<string, TimelineGroup>();
  for (const item of items) {
    const timestamp = projectionTimestamp(item);
    const label =
      timestamp === null
        ? 'Date unavailable'
        : conversationGroupLabel(
            new Date(timestamp).toISOString(),
            nowEpochMilliseconds,
          );
    const group = groups.get(label);
    if (group === undefined) {
      groups.set(label, {label, items: [item]});
    } else {
      group.items.push(item);
    }
  }
  return [...groups.values()];
}

export type ReadPageState = {
  windowStatus: 'complete' | 'more' | 'incomplete' | 'unknown';
  complete: boolean;
  hasMore: boolean;
  nextCursor: string | null;
  completenessStatus:
    | 'complete'
    | 'incomplete'
    | 'degraded'
    | 'partial'
    | 'unknown';
  reasons: string[];
};

export type DomainRead<T extends DesktopReadProjection> = {
  apiContract?: 'omi';
  items: T[];
  page: ReadPageState;
};

export type TaskRead = DomainRead<TaskProjection> & {
  accountEpoch: number | null;
};

export type DomainReadOutcome<T extends DesktopReadProjection> =
  | {status: 'success'; value: DomainRead<T>}
  | {status: 'error'; error: string};

export type TaskReadOutcome =
  | {status: 'success'; value: TaskRead}
  | {status: 'error'; error: string};

export type DesktopReadOutcomes = {
  conversations: DomainReadOutcome<ConversationProjection>;
  memories: DomainReadOutcome<MemoryProjection>;
  tasks: TaskReadOutcome;
};

export const desktopCloudBaseURL = 'https://api.omi.me';
export const desktopBackendConfigurationCopy =
  'Sign in to Omi cloud to load conversations and memories.';
export const desktopBackendUnauthorizedCopy =
  'Omi cloud needs a signed-in session.';
export const desktopBackendServiceCopy =
  'The selected Omi service is unavailable. Check the connection, then retry.';
export const desktopLocalBackendServiceCopy =
  'The configured local Omi service is unavailable. Check its connection, then retry.';
export const desktopProjectionUnavailableCopy =
  'This saved data is not available from the selected Omi service yet. Retry after its persisted projection is connected.';
export const desktopBackendForbiddenCopy =
  'This saved data is not available for this account.';
const desktopReadFailureCopy =
  'This saved data could not be loaded. Retry without changing it.';
const desktopRecoveryGenericCopy =
  'Omi could not load saved conversations or memories. Your saved data has not been changed.';

export function desktopRecoveryCopy(
  conversations: DomainReadOutcome<ConversationProjection>,
  memories: DomainReadOutcome<MemoryProjection>,
): string {
  for (const outcome of [conversations, memories]) {
    if (
      outcome.status === 'error' &&
      (outcome.error === desktopBackendConfigurationCopy ||
        outcome.error === desktopBackendUnauthorizedCopy ||
        outcome.error === desktopBackendServiceCopy ||
        outcome.error === desktopLocalBackendServiceCopy ||
        outcome.error === desktopProjectionUnavailableCopy ||
        outcome.error === desktopBackendForbiddenCopy)
    ) {
      return outcome.error;
    }
  }
  return desktopRecoveryGenericCopy;
}

class DesktopProjectionUnavailableError extends Error {}
export class ConversationCursorExpiredError extends Error {}
export class TaskCursorExpiredError extends Error {}

function nativeErrorCode(value: unknown): string | null {
  if (value === null || typeof value !== 'object') {
    return null;
  }
  const code = (value as {code?: unknown}).code;
  return typeof code === 'string' ? code : null;
}

export function desktopReadErrorCopy(error: unknown): string {
  const code = nativeErrorCode(error);
  if (
    code === 'OMI_HTTP_UNCONFIGURED' ||
    (error instanceof Error &&
      error.message === 'Native HTTP configuration is unavailable')
  ) {
    return desktopBackendConfigurationCopy;
  }
  if (code === 'unauthorized' || code === 'OMI_HTTP_UNAUTHORIZED') {
    return desktopBackendUnauthorizedCopy;
  }
  if (
    code === 'OMI_HTTP_TRANSPORT' ||
    (error instanceof Error && error.message === 'Native HTTP transport failed')
  ) {
    return desktopBackendServiceCopy;
  }
  const message = error instanceof Error ? error.message : null;
  return message !== null &&
    [
      desktopBackendConfigurationCopy,
      desktopBackendUnauthorizedCopy,
      desktopBackendServiceCopy,
      desktopLocalBackendServiceCopy,
      desktopProjectionUnavailableCopy,
      desktopBackendForbiddenCopy,
      desktopReadFailureCopy,
    ].includes(message)
    ? message
    : desktopReadFailureCopy;
}

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

function text(value: unknown, label: string): string {
  if (typeof value !== 'string') {
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
  expectedApiContract: 'omi' | 'canonical' = 'canonical',
): Promise<unknown> {
  const response = await backend.request({
    id,
    method: 'GET',
    path,
    expectedApiContract,
  });
  if (response.status !== 200) {
    if (
      response.status === 400 &&
      id === 'desktop-tasks-read' &&
      path.includes('?cursor=')
    ) {
      throw new TaskCursorExpiredError('Tasks changed. Refresh the list.');
    }
    if (
      response.status === 400 &&
      id === 'desktop-conversations-read' &&
      path.includes('&cursor=')
    ) {
      throw new ConversationCursorExpiredError(
        'Conversations changed. Refresh the list.',
      );
    }
    if (response.status === 401) {
      const unauthorized = new Error(
        desktopBackendUnauthorizedCopy,
      ) as Error & {
        code: string;
      };
      unauthorized.code = 'unauthorized';
      throw unauthorized;
    }
    if (response.status === 403) {
      throw new Error(desktopBackendForbiddenCopy);
    }
    if (response.status === 503 && response.body !== null) {
      try {
        const body = object(JSON.parse(response.body), `${id} error`);
        const error = object(body.error, `${id} error detail`);
        if (
          error.code === 'projection_unavailable' &&
          error.retryable === true &&
          error.action === 'retry'
        ) {
          throw new DesktopProjectionUnavailableError(
            desktopProjectionUnavailableCopy,
          );
        }
      } catch (error) {
        if (error instanceof DesktopProjectionUnavailableError) {
          throw error;
        }
      }
    }
    throw new Error(
      response.status >= 500
        ? desktopBackendServiceCopy
        : desktopReadFailureCopy,
    );
  }
  return parseJson(response.body, id);
}

function validatePage(
  value: unknown,
  label: string,
  completenessVersion:
    | 'recall-completeness-v1'
    | 'tasks-completeness-v1'
    | 'conversations-completeness-v1',
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
  if (
    !['complete', 'incomplete', 'degraded', 'partial'].includes(
      completenessStatus,
    )
  ) {
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

function epochMillisecondsTimestamp(value: unknown, label: string): string {
  if (
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    !Number.isFinite(new Date(value).getTime())
  ) {
    throw new Error(`${label} is malformed`);
  }
  return new Date(value).toISOString();
}
function nullableEpochMillisecondsTimestamp(
  value: unknown,
  label: string,
): string | null {
  return value === null ? null : epochMillisecondsTimestamp(value, label);
}

export async function loadConversations(
  backend: OmiBackend,
  cursor: string | null = null,
): Promise<DomainRead<ConversationProjection>> {
  if ((await backend.getApiContract?.()) === 'omi') {
    return loadOmiConversations(
      path => read(backend, 'desktop-omi-read', path, 'omi'),
      cursor,
    );
  }
  if (cursor !== null && (cursor.length === 0 || cursor.length > 16384)) {
    throw new Error('Conversation cursor is malformed');
  }
  const value = await read(
    backend,
    'desktop-conversations-read',
    `/v1/conversations?limit=50${
      cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`
    }`,
  );
  const page = validatePage(
    value,
    'Conversations response',
    'conversations-completeness-v1',
  );
  const ids = new Set<string>();
  const items = page.items.map((record, index) => {
    const id = string(record.id, `Conversation ${index} id`);
    if (ids.has(id)) {
      throw new Error('Conversation IDs are duplicated');
    }
    ids.add(id);
    const title = text(record.title, `Conversation ${index} title`);
    const summary = text(record.overview, `Conversation ${index} overview`);
    const createdAt = epochMillisecondsTimestamp(
      record.createdAt,
      `Conversation ${index} createdAt`,
    );
    const updatedAt = epochMillisecondsTimestamp(
      record.updatedAt,
      `Conversation ${index} updatedAt`,
    );
    const startedAt = nullableEpochMillisecondsTimestamp(
      record.startedAt,
      `Conversation ${index} startedAt`,
    );
    const finishedAt = nullableEpochMillisecondsTimestamp(
      record.finishedAt,
      `Conversation ${index} finishedAt`,
    );
    const source = string(record.source, `Conversation ${index} source`);
    const status = string(record.status, `Conversation ${index} status`);
    const discarded = boolean(
      record.discarded,
      `Conversation ${index} discarded`,
    );
    if (!isOptionalCaptureTimestamp(record.capturedAtMs)) {
      throw new Error(`Conversation ${index} capturedAtMs is malformed`);
    }
    const starred = boolean(record.starred, `Conversation ${index} starred`);
    const visibility = string(
      record.visibility,
      `Conversation ${index} visibility`,
    );
    if (!['public', 'private', 'shared'].includes(visibility)) {
      throw new Error(`Conversation ${index} visibility is malformed`);
    }
    const locked = boolean(record.isLocked, `Conversation ${index} isLocked`);
    if (record.folderId !== null && typeof record.folderId !== 'string') {
      throw new Error(`Conversation ${index} folderId is malformed`);
    }
    return {
      kind: 'conversation' as const,
      ...(record.capturedAtMs === undefined
        ? {}
        : {capturedAtMs: record.capturedAtMs}),
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
      source,
      visibility: visibility as ConversationProjection['visibility'],
      folderId: record.folderId as string | null,
      locked,
      discarded,
    };
  });
  return {items, page: page.page};
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
  if ((await backend.getApiContract?.()) === 'omi') {
    return loadOmiMemories(
      path => read(backend, 'desktop-omi-read', path, 'omi'),
      cursor,
    );
  }
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

export async function loadTasks(
  backend: OmiBackend,
  cursor: string | null = null,
): Promise<TaskRead> {
  if ((await backend.getApiContract?.()) === 'omi') {
    return loadOmiTasks(
      path => read(backend, 'desktop-omi-read', path, 'omi'),
      cursor,
    );
  }
  if (cursor !== null && (cursor.length === 0 || cursor.length > 16384))
    throw new Error('Task cursor is malformed');
  const value = await read(
    backend,
    'desktop-tasks-read',
    `/v1/tasks${
      cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`
    }`,
  );
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
  if (new Set(items.map(item => item.id)).size !== items.length)
    throw new Error('Task IDs are duplicated');
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
  const outcome = <T extends DomainRead<DesktopReadProjection>>(
    result: PromiseSettledResult<T>,
  ): {status: 'success'; value: T} | {status: 'error'; error: string} =>
    result.status === 'fulfilled'
      ? {status: 'success', value: result.value}
      : {
          status: 'error',
          error: desktopReadErrorCopy(result.reason),
        };
  return {
    conversations: outcome(conversations),
    memories: outcome(memories),
    tasks: outcome(tasks),
  };
}
