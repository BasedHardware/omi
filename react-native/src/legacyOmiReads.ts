import {isOptionalCaptureTimestamp} from './captureTimestamp';
import {
  conversationDiscardedTranscriptCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationTranscriptEndSeconds,
  memoryCaptureDeviceCopy,
  taskDisplayTitle,
  taskExportCopy,
  visibleDisplayText,
  type ConversationProjection,
  type DomainRead,
  type MemoryProjection,
  type ReadPageState,
  type TaskRead,
} from './desktopReadClient';

type Read = (path: `/${string}`) => Promise<unknown>;
const limit = 50;
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Omi response is malformed');
  return value as Record<string, unknown>;
}
function text(value: unknown, fallback?: string): string {
  if (value === undefined || value === null) {
    if (fallback !== undefined) return fallback;
  }
  if (typeof value !== 'string') throw new Error('Omi text is malformed');
  return value;
}
function id(value: unknown): string {
  const result = text(value);
  if (!result) throw new Error('Omi ID is malformed');
  return result;
}
function bool(value: unknown, fallback = false): boolean {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'boolean') throw new Error('Omi boolean is malformed');
  return value;
}
function date(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T/.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    throw new Error('Omi timestamp is malformed');
  return new Date(value).toISOString();
}
function milliseconds(value: unknown): number | null {
  const parsed = date(value);
  return parsed === null ? null : Date.parse(parsed);
}
function integer(value: unknown, nonnegative = false): number {
  if (value === undefined || value === null) return 0;
  if (
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    (nonnegative && value < 0)
  )
    throw new Error('Omi order is malformed');
  return value;
}
function rows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length > limit)
    throw new Error('Omi list is malformed');
  const seen = new Set<string>();
  return value.map(item => {
    const row = object(item),
      key = id(row.id);
    if (seen.has(key)) throw new Error('Omi IDs are duplicated');
    seen.add(key);
    return row;
  });
}
function offset(cursor: string | null): number {
  if (cursor === null) return 0;
  if (!/^omi-offset:[1-9][0-9]*$/.test(cursor))
    throw new Error('Omi cursor is malformed');
  const value = Number(cursor.slice(11));
  if (!Number.isSafeInteger(value) || value > Number.MAX_SAFE_INTEGER - limit)
    throw new Error('Omi cursor is malformed');
  return value;
}
function page(
  start: number,
  count: number,
  hasMore = count === limit,
  truncated = false,
  known = false,
): ReadPageState {
  return {
    windowStatus: truncated
      ? 'incomplete'
      : hasMore
      ? 'more'
      : known
      ? 'complete'
      : 'unknown',
    complete: known && !hasMore && !truncated,
    hasMore: hasMore && count > 0 && !truncated,
    nextCursor:
      hasMore && count > 0 && !truncated ? `omi-offset:${start + count}` : null,
    completenessStatus: truncated
      ? 'incomplete'
      : known
      ? 'complete'
      : 'unknown',
    reasons: truncated
      ? ['The service returned a partial list. Refresh to retry.']
      : known
      ? []
      : ['The Omi API does not provide snapshot completeness for this list.'],
  };
}
function photoCount(value: unknown): number {
  if (value === undefined || value === null) {
    return 0;
  }
  if (!Array.isArray(value)) {
    throw new Error('Omi photos are malformed');
  }
  return value.length;
}
function finiteClock(value: unknown): number {
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (value.trim() === '' || !Number.isFinite(parsed)) {
      throw new Error('Omi transcript is malformed');
    }
    return parsed;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error('Omi transcript is malformed');
  }
  return value;
}
function discardedTranscriptSegments(value: unknown): {
  text: string;
  speaker: string | null;
  isUser: boolean;
  start: number;
  end: number;
}[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value) || value.length > 20000) {
    throw new Error('Omi transcript is malformed');
  }
  return value.map(raw => {
    const segment = object(raw);
    return {
      text: text(segment.text, ''),
      speaker: segment.speaker == null ? null : text(segment.speaker),
      isUser: bool(segment.is_user),
      start: finiteClock(segment.start),
      end: finiteClock(segment.end),
    };
  });
}
export async function loadOmiConversations(
  read: Read,
  cursor: string | null,
): Promise<DomainRead<ConversationProjection>> {
  const start = offset(cursor);
  const records = rows(
    await read(`/v1/conversations?limit=${limit}&offset=${start}`),
  );
  const items = records.map(row => {
    const structured = object(row.structured);
    const structuredTitle = text(structured.title, ''),
      summary = text(structured.overview, '');
    const discarded = bool(row.discarded);
    const discardedSegments = discarded
      ? discardedTranscriptSegments(row.transcript_segments)
      : [];
    const discardedExcerpt = discarded
      ? conversationDiscardedTranscriptCopy(discardedSegments)
      : null;
    const transcriptEndSeconds = discarded
      ? conversationTranscriptEndSeconds(discardedSegments)
      : null;
    const title =
      discardedExcerpt !== null ? discardedExcerpt : structuredTitle;
    const emoji = visibleDisplayText(text(structured.emoji, ''));
    const category = visibleDisplayText(text(structured.category, ''));
    const createdAt = date(row.created_at);
    if (createdAt === null)
      throw new Error('Omi conversation creation time is malformed');
    const visibility = text(row.visibility, 'private');
    if (!['private', 'public', 'shared'].includes(visibility))
      throw new Error('Omi visibility is malformed');
    const status = text(row.status, 'completed');
    const photos = photoCount(row.photos);
    if (!isOptionalCaptureTimestamp(row.captured_at_ms)) {
      throw new Error('Omi captured_at_ms is malformed');
    }
    return {
      kind: 'conversation' as const,
      id: id(row.id),
      title,
      summary,
      searchableText: `${conversationDisplayTitle({
        title,
        status,
      })}\n${conversationDisplaySummary({summary, status})}`,
      createdAt,
      updatedAt: date(row.updated_at),
      startedAt: date(row.started_at),
      finishedAt: date(row.finished_at),
      starred: bool(row.starred),
      status,
      source: text(row.source, row.source === null ? 'unknown' : 'omi'),
      visibility: visibility as ConversationProjection['visibility'],
      folderId: row.folder_id == null ? null : text(row.folder_id),
      locked: bool(row.is_locked),
      discarded,
      ...(emoji === '' ? {} : {emoji}),
      ...(category === '' ? {} : {category}),
      ...(photos === 0 ? {} : {photoCount: photos}),
      ...(row.captured_at_ms === undefined
        ? {}
        : {capturedAtMs: row.captured_at_ms}),
      ...(transcriptEndSeconds === null ? {} : {transcriptEndSeconds}),
    };
  });
  return {apiContract: 'omi', items, page: page(start, items.length)};
}
export async function loadOmiMemories(
  read: Read,
  cursor: string | null,
): Promise<DomainRead<MemoryProjection>> {
  const start = offset(cursor);
  const records = rows(
    await read(`/v3/memories?limit=${limit}&offset=${start}`),
  );
  const items = records.map(row => {
    const content = text(row.content),
      created = milliseconds(row.created_at);
    const conversation =
      row.conversation_id == null ? null : id(row.conversation_id);
    const ledgerSlot = visibleDisplayText(text(row.slot, ''));
    const ledgerKind = visibleDisplayText(text(row.kind, ''));
    const ledgerSchema = visibleDisplayText(
      text(row.ledger_schema_version, ''),
    );
    const ledgerBody = visibleDisplayText(text(row.body, ''));
    const playbook =
      ledgerSchema === 'knowledge_ledger.v1' && ledgerKind === 'document'
        ? ledgerBody
        : '';
    const captureDeviceLabel = memoryCaptureDeviceCopy(
      text(row.primary_capture_device, ''),
    );
    return {
      kind: 'memory' as const,
      id: id(row.id),
      title: content,
      summary: content,
      searchableText: content,
      citations: conversation === null ? [] : [conversation],
      timestamp: created === null ? null : created / 1000,
      provenance: {
        label: null,
        synthesisVersion: null,
        inputDigest: null,
        outputDigest: null,
      },
      ...(ledgerSlot === '' ? {} : {ledgerSlot}),
      ...(playbook === '' ? {} : {ledgerBody: playbook}),
      ...(bool(row.is_baseline) ? {isBaseline: true} : {}),
      ...(captureDeviceLabel === null ? {} : {captureDeviceLabel}),
      ...(bool(row.is_locked) ? {locked: true} : {}),
    };
  });
  return {apiContract: 'omi', items, page: page(start, items.length)};
}
export async function loadOmiTasks(
  read: Read,
  cursor: string | null,
): Promise<TaskRead> {
  const start = offset(cursor);
  const envelope = object(
    await read(`/v1/action-items?limit=${limit}&offset=${start}`),
  );
  if (typeof envelope.has_more !== 'boolean')
    throw new Error('Omi pagination is malformed');
  const records = rows(envelope.action_items);
  const items = records.map(row => {
    const description = text(row.description),
      completed = bool(row.completed);
    if (typeof row.completed !== 'boolean')
      throw new Error('Omi task completion is malformed');
    const evidence = row.provenance ?? [];
    if (!Array.isArray(evidence))
      throw new Error('Omi task provenance is malformed');
    const exportCopy = taskExportCopy(
      bool(row.exported, false),
      row.export_platform === undefined || row.export_platform === null
        ? undefined
        : text(row.export_platform),
    );
    const rawTaskId = row.taskId ?? row.task_id;
    const parsedTaskId =
      rawTaskId === undefined || rawTaskId === null
        ? undefined
        : text(rawTaskId);
    const taskId =
      parsedTaskId === undefined || visibleDisplayText(parsedTaskId) === ''
        ? undefined
        : parsedTaskId;
    return {
      kind: 'task' as const,
      id: id(row.id),
      title: description,
      summary: completed ? 'Completed' : 'Pending',
      searchableText: taskDisplayTitle({title: description}),
      completed,
      completedAt: milliseconds(row.completed_at),
      dueAt: milliseconds(row.due_at),
      owner: row.owner == null ? null : text(row.owner),
      source: text(row.source, 'legacy'),
      provenance: evidence.map(item => {
        const ref = object(item);
        id(ref.id);
        return JSON.stringify(ref);
      }),
      sortOrder: integer(row.sort_order),
      indentLevel: integer(row.indent_level, true),
      createdAt: milliseconds(row.created_at),
      updatedAt: milliseconds(row.updated_at),
      revision: null,
      ...(exportCopy === null ? {} : {exportCopy}),
      ...(taskId === undefined ? {} : {taskId}),
    };
  });
  return {
    items,
    page: page(
      start,
      items.length,
      envelope.has_more,
      bool(envelope.truncated),
      true,
    ),
    accountEpoch: null,
    apiContract: 'omi',
  };
}
