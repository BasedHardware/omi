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

export function conversationDisplayTitle(item: {
  title: string;
  status: string;
}): string {
  const title = item.title.trim();
  if (title !== '') {
    return title;
  }
  return item.status === 'processing'
    ? 'Processing conversation…'
    : 'Conversation title unavailable';
}

export function conversationDisplaySummary(item: {
  summary: string;
  status: string;
}): string {
  const summary = item.summary.trim();
  if (summary !== '') {
    return summary;
  }
  return item.status === 'processing'
    ? 'Conversation summary is not ready yet.'
    : 'Conversation summary unavailable';
}

export function conversationStatusCopy(status: string): string {
  const trimmed = status.trim();
  if (trimmed === 'in_progress') {
    return 'In progress';
  }
  if (trimmed === 'processing') {
    return 'Processing';
  }
  if (trimmed === 'merging') {
    return 'Merging';
  }
  if (trimmed === 'completed') {
    return 'Completed';
  }
  if (trimmed === 'failed') {
    return 'Failed';
  }
  return trimmed === '' ? 'Status unavailable' : trimmed;
}

export function accountWireCopy(value: string, unavailable: string): string {
  const trimmed = value.trim();
  if (trimmed === '') {
    return unavailable;
  }
  const words = trimmed.split(/[_-]+/).filter(part => part !== '');
  if (words.length === 0) {
    return unavailable;
  }
  return words
    .map((word, index) => {
      const lower = word.toLowerCase();
      return index === 0
        ? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`
        : lower;
    })
    .join(' ');
}

export function accountFieldCopy(
  value: string | null | undefined,
  unset: string,
): string {
  const trimmed = value?.trim() ?? '';
  return trimmed !== '' ? trimmed : unset;
}

export function connectionIdentityCopy(
  identity: {displayName: string; email: string} | null,
): string {
  if (identity === null) {
    return 'Identity unavailable for this connection.';
  }
  return (
    [identity.displayName, identity.email]
      .map(part => part.trim())
      .filter(part => part !== '')
      .join(' · ') || 'Identity unavailable for this connection.'
  );
}

export function subscriptionPlanCopy(plan: string): string {
  return accountWireCopy(plan, 'Plan unavailable');
}

export function subscriptionStatusCopy(status: string): string {
  return accountWireCopy(status, 'Plan unavailable');
}

export function dataProtectionCopy(level: string): string {
  return accountWireCopy(level, 'Data protection unavailable');
}

export function developerWebhookTypeCopy(type: string): string {
  if (type === 'memory_created') {
    return 'Conversation Events';
  }
  if (type === 'realtime_transcript') {
    return 'Real-time Transcript';
  }
  if (type === 'audio_bytes') {
    return 'Audio Bytes';
  }
  if (type === 'day_summary') {
    return 'Day Summary';
  }
  return accountWireCopy(type, 'Webhook unavailable');
}

export function developerWebhookStatusCopy(enabled: boolean | null): string {
  if (enabled === null) {
    return 'Status unavailable';
  }
  return enabled ? 'Enabled' : 'Disabled';
}

export function developerWebhookRowCopy(webhook: {
  enabled: boolean | null;
  url: string | null;
}): string {
  const url = webhook.url?.trim() ?? '';
  return [developerWebhookStatusCopy(webhook.enabled), url !== '' ? url : null]
    .filter(item => item !== null)
    .join(' · ');
}

export function appCategoryCopy(category: string): string {
  return accountWireCopy(category, '');
}

export function appDisplayName(name: string): string {
  return accountFieldCopy(name, 'App name unavailable');
}

export function deviceDisplayName(name: string): string {
  return accountFieldCopy(name, 'Device name unavailable');
}

export function appDisplaySource(app: {
  author: string;
  category: string;
  description: string;
}): string {
  const author = app.author.trim();
  if (author !== '') {
    return author;
  }
  const category = appCategoryCopy(app.category);
  if (category !== '') {
    return category;
  }
  const description = app.description.trim();
  return description !== '' ? description : 'App details unavailable';
}

export function chatAttachmentDisplayName(name: string): string {
  return accountFieldCopy(name, 'Attachment name unavailable');
}

export function chatMessageDisplayText(
  message: {
    text: string;
    generationOutcome: 'completed' | 'cancelled' | 'failed' | null;
    generationRetryable?: boolean;
    attachments?: readonly {displayName: string}[];
  },
  cancelledEmptyCopy = 'Response stopped',
): string {
  if (message.generationOutcome === 'failed') {
    return message.generationRetryable === true
      ? 'Response failed. Try again.'
      : 'Response failed.';
  }
  const text = message.text.trim();
  const attachmentLines = (message.attachments ?? []).map(attachment =>
    chatAttachmentDisplayName(attachment.displayName),
  );
  if (text !== '') {
    return attachmentLines.length > 0
      ? `${text}\n${attachmentLines.join('\n')}`
      : text;
  }
  if (message.generationOutcome === 'cancelled') {
    return cancelledEmptyCopy;
  }
  if (attachmentLines.length > 0) {
    return attachmentLines.join('\n');
  }
  return 'Message text unavailable';
}

export function chatSenderCopy(sender: 'human' | 'ai' | 'unknown'): string {
  if (sender === 'human') {
    return 'You';
  }
  if (sender === 'ai') {
    return 'Omi';
  }
  return 'Sender unavailable';
}

export function memoryDisplayTitle(item: {
  title: string;
  summary: string;
}): string {
  const title = item.title.trim();
  const summary = item.summary.trim();
  return visibleMemoryText(title !== '' ? title : summary);
}

export function memoryDisplayBody(item: {
  title: string;
  summary: string;
}): string {
  const title = item.title.trim();
  const summary = item.summary.trim();
  return visibleMemoryText(summary !== '' ? summary : title);
}

export function memoryCitationCopy(citations: readonly string[]): string {
  return citations.length === 1
    ? '1 citation'
    : `${citations.length} citations`;
}

export function memorySynthesisCopy(item: {
  provenance: {synthesisVersion: string | null};
}): string | null {
  const version = item.provenance.synthesisVersion?.trim() ?? '';
  return version !== '' ? 'Synthesized memory' : null;
}

export function epochMilliseconds(value: number): number {
  return value > 100_000_000_000 ? value : value * 1000;
}

export function formatTaskDue(dueAt: number | null): string {
  if (dueAt === null) {
    return 'No due date';
  }
  if (!Number.isFinite(dueAt) || dueAt <= 0) {
    return 'Date unavailable';
  }
  return new Date(epochMilliseconds(dueAt)).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function taskDisplaySummary(item: {
  completed: boolean;
  dueAt: number | null;
}): string {
  if (item.completed) {
    return 'Completed';
  }
  if (item.dueAt === null) {
    return 'Pending';
  }
  if (!Number.isFinite(item.dueAt) || item.dueAt <= 0) {
    return 'Date unavailable';
  }
  return `Due ${formatTaskDue(item.dueAt)}`;
}

export function taskDisplayTitle(item: {title: string}): string {
  const title = item.title.trim();
  return title !== '' ? title : 'Task title unavailable';
}

function visibleMemoryText(text: string): string {
  const parsed = parseMemoryText(text);
  const body = parsed.body.trim();
  return body !== '' ? body : 'Memory text unavailable';
}

export function conversationGroupLabel(
  value: string,
  nowEpochMilliseconds: number,
): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return 'Date unavailable';
  }
  const date = new Date(timestamp);
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

export function conversationDayLabel(
  startedAt: string | null,
  createdAt: string,
  nowEpochMilliseconds: number,
): string {
  return conversationGroupLabel(startedAt ?? createdAt, nowEpochMilliseconds);
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
  if (dueAt === null || !Number.isFinite(dueAt) || dueAt <= 0) {
    return 'Later';
  }
  const today = Math.floor(nowMilliseconds / 86400000);
  const dueDay = Math.floor(epochMilliseconds(dueAt) / 86400000);
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
      : item.createdAt === null
      ? null
      : epochMilliseconds(item.createdAt);
  return timestamp === null || !Number.isFinite(timestamp) ? null : timestamp;
}

export function clockLabel(
  timestampMs: number,
  nowEpochMilliseconds: number,
): string {
  if (!Number.isFinite(timestampMs) || timestampMs <= 0) {
    return '';
  }
  const day = conversationGroupLabel(
    new Date(timestampMs).toISOString(),
    nowEpochMilliseconds,
  );
  const time = new Date(timestampMs).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
  return day === 'Today' ? time : `${day} · ${time}`;
}

export function chatClockLabel(
  createdAt: number,
  nowEpochMilliseconds: number,
): string {
  return clockLabel(epochMilliseconds(createdAt), nowEpochMilliseconds);
}

export function projectionClockLabel(
  item: DesktopReadProjection,
  nowEpochMilliseconds: number,
): string {
  const timestamp = projectionTimestamp(item);
  if (timestamp === null || timestamp <= 0) {
    return 'Time unavailable';
  }
  return clockLabel(timestamp, nowEpochMilliseconds);
}

export function homeSearchItems(
  reads: DesktopReadProjection[],
  tasks: readonly TaskProjection[] | null,
  query: string,
): DesktopReadProjection[] {
  const normalized = query.trim().toLocaleLowerCase();
  const matches = (item: DesktopReadProjection): boolean =>
    normalized === '' ||
    item.searchableText.toLocaleLowerCase().includes(normalized);
  return [...reads.filter(matches), ...(tasks ?? []).filter(matches)].sort(
    (left, right) => {
      const leftTs = projectionTimestamp(left);
      const rightTs = projectionTimestamp(right);
      return (
        (rightTs ?? Number.NEGATIVE_INFINITY) -
        (leftTs ?? Number.NEGATIVE_INFINITY)
      );
    },
  );
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
  items: T[];
  page: ReadPageState;
};

export type TaskRead = DomainRead<TaskProjection> & {
  apiContract?: 'omi';
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
export const desktopBackendUnavailableCopy =
  'This saved data is not available from the selected Omi service yet.';
export const desktopAppsUnavailableCopy =
  'Apps are not available from the selected Omi service yet.';
export const desktopAccountSettingUnavailableCopy =
  'This account setting is not available from the selected Omi service yet.';
export const desktopBackendForbiddenCopy =
  'This saved data is not available for this account.';
const desktopReadFailureCopy =
  'This saved data could not be loaded. Retry without changing it.';
const desktopRecoveryGenericCopy =
  'Omi could not load saved conversations or memories. Your saved data has not been changed.';

export function desktopReadsCanRetry(
  outcomes: DesktopReadOutcomes | null,
): boolean {
  if (outcomes === null) {
    return true;
  }
  const errors = [
    outcomes.conversations,
    outcomes.memories,
    outcomes.tasks,
  ].filter(
    (outcome): outcome is {status: 'error'; error: string} =>
      outcome.status === 'error',
  );
  return (
    errors.length === 0 ||
    errors.some(outcome => outcome.error !== desktopBackendUnavailableCopy)
  );
}

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
        outcome.error === desktopBackendUnavailableCopy ||
        outcome.error === desktopBackendForbiddenCopy)
    ) {
      return outcome.error;
    }
  }
  return desktopRecoveryGenericCopy;
}

class DesktopProjectionUnavailableError extends Error {}
class DesktopBackendUnavailableError extends Error {}
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
      desktopBackendUnavailableCopy,
      desktopAppsUnavailableCopy,
      desktopAccountSettingUnavailableCopy,
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
        if (error.retryable === false) {
          throw new DesktopBackendUnavailableError(
            desktopBackendUnavailableCopy,
          );
        }
      } catch (error) {
        if (
          error instanceof DesktopProjectionUnavailableError ||
          error instanceof DesktopBackendUnavailableError
        ) {
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
    const source = text(record.source, `Conversation ${index} source`);
    const status = text(record.status, `Conversation ${index} status`);
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
      searchableText: `${conversationDisplayTitle({
        title,
        status,
      })}\n${conversationDisplaySummary({summary, status})}`,
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
    const result = await loadOmiMemories(
      path => read(backend, 'desktop-omi-read', path, 'omi'),
      cursor,
    );
    return {
      page: result.page,
      items: result.items.map(item => {
        const parsed = parseMemoryText(
          item.summary !== '' ? item.summary : item.title,
        );
        return {
          ...item,
          title: parsed.body,
          summary: parsed.body,
          searchableText: memoryDisplayTitle({
            title: parsed.body,
            summary: parsed.body,
          }),
          provenance: {
            ...item.provenance,
            label: parsed.provenanceLabel ?? item.provenance.label,
          },
        };
      }),
    };
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
    const citations =
      item.citations === undefined
        ? []
        : stringArray(item.citations, `Memory ${index} citations`);
    let synthesisVersion: string | null = null;
    let inputDigest: string | null = null;
    let outputDigest: string | null = null;
    if (item.provenance !== undefined) {
      const provenance = object(item.provenance, `Memory ${index} provenance`);
      synthesisVersion = string(
        provenance.synthesisVersion,
        `Memory ${index} synthesisVersion`,
      );
      inputDigest = string(
        provenance.inputDigest,
        `Memory ${index} inputDigest`,
      );
      outputDigest = string(
        provenance.outputDigest,
        `Memory ${index} outputDigest`,
      );
    }
    return {
      kind: 'memory' as const,
      id,
      title: parsedText.body,
      summary: parsedText.body,
      searchableText: `${memoryDisplayTitle({
        title: parsedText.body,
        summary: parsedText.body,
      })}\n${citations.join('\n')}`,
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
    const description = text(item.description, `Task ${index} description`);
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
    const source = text(item.source, `Task ${index} source`);
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
        : text(item.revision, `Task ${index} revision`);
    return {
      kind: 'task' as const,
      id,
      title: description,
      summary: completed
        ? 'Completed'
        : dueAt === null
        ? 'Pending'
        : `Due ${dueAt}`,
      searchableText: taskDisplayTitle({title: description}),
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
