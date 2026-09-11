import {decodeBase64} from './base64';
import type {
  ChatHistoryPage,
  ChatMessage,
  ChatMessageAttachment,
} from './chatClient';
import {chatEvidenceCopy, visibleDisplayText} from './desktopReadClient';

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Omi chat message is malformed');
  }
  return value as Record<string, unknown>;
}

function parseOmiChatFiles(
  files: unknown,
  filesId: unknown,
): ChatMessageAttachment[] {
  if (files === undefined || files === null) {
    if (filesId === undefined || filesId === null) {
      return [];
    }
    if (
      !Array.isArray(filesId) ||
      filesId.length > 50 ||
      !filesId.every(id => typeof id === 'string')
    ) {
      throw new Error('Omi chat files are malformed');
    }
    return [];
  }
  if (!Array.isArray(files) || files.length > 50) {
    throw new Error('Omi chat files are malformed');
  }
  const ids =
    filesId === undefined || filesId === null
      ? []
      : Array.isArray(filesId) &&
        filesId.length <= 50 &&
        filesId.every(id => typeof id === 'string')
      ? filesId
      : null;
  if (ids === null) {
    throw new Error('Omi chat files are malformed');
  }
  if (files.length === 0 || ids.length === 0) {
    return [];
  }
  return files.map(raw => {
    const row = object(raw);
    const createdAt =
      typeof row.created_at === 'string' ? Date.parse(row.created_at) : NaN;
    if (
      typeof row.id !== 'string' ||
      row.id.length === 0 ||
      typeof row.name !== 'string' ||
      typeof row.mime_type !== 'string' ||
      typeof row.openai_file_id !== 'string' ||
      !Number.isFinite(createdAt)
    ) {
      throw new Error('Omi chat files are malformed');
    }
    if (
      row.thumbnail !== undefined &&
      row.thumbnail !== null &&
      typeof row.thumbnail !== 'string'
    ) {
      throw new Error('Omi chat files are malformed');
    }
    const thumbnail =
      typeof row.thumbnail === 'string' ? row.thumbnail : undefined;
    return {
      id: row.id,
      displayName: row.name,
      mediaType: row.mime_type,
      ...(visibleDisplayText(thumbnail ?? '') === '' ? {} : {thumbnail}),
    };
  });
}

function parseOmiChatMemories(
  value: unknown,
): {title: string; emoji?: string}[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value) || value.length > 50) {
    throw new Error('Omi chat memories are malformed');
  }
  return value.map(raw => {
    const row = object(raw);
    const structured = object(row.structured);
    if (
      typeof structured.title !== 'string' ||
      typeof structured.emoji !== 'string'
    ) {
      throw new Error('Omi chat memories are malformed');
    }
    return {
      title: structured.title,
      ...(structured.emoji === '' ? {} : {emoji: structured.emoji}),
    };
  });
}

function parseOmiChatChart(
  value: unknown,
): {title: string; points: {label: string; value: number}[]} | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const row = object(value);
  if (
    (row.chart_type !== 'line' && row.chart_type !== 'bar') ||
    typeof row.title !== 'string' ||
    !Array.isArray(row.datasets)
  ) {
    return undefined;
  }
  if (
    row.datasets.length === 0 ||
    row.datasets.length > 20 ||
    row.datasets[0] === null ||
    typeof row.datasets[0] !== 'object' ||
    Array.isArray(row.datasets[0])
  ) {
    return undefined;
  }
  const dataset = row.datasets[0] as Record<string, unknown>;
  if (
    !Array.isArray(dataset.data_points) ||
    dataset.data_points.length === 0 ||
    dataset.data_points.length > 200
  ) {
    return undefined;
  }
  const points: {label: string; value: number}[] = [];
  for (const raw of dataset.data_points) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      return undefined;
    }
    const point = raw as Record<string, unknown>;
    let value: number;
    if (typeof point.value === 'string') {
      const parsed = Number(point.value);
      if (point.value.trim() === '' || !Number.isFinite(parsed)) {
        return undefined;
      }
      value = parsed;
    } else if (
      typeof point.value === 'number' &&
      Number.isFinite(point.value)
    ) {
      value = point.value;
    } else {
      return undefined;
    }
    if (typeof point.label !== 'string') {
      return undefined;
    }
    points.push({label: point.label, value});
  }
  return {title: row.title, points};
}

const conversationEvidenceKinds = new Set([
  'conversation_summary',
  'conversation_segment',
]);

function parseOmiChatEvidenceRaw(value: unknown): {
  kind: string;
  state: string;
  title?: string;
  summary?: string;
}[] {
  if (value === undefined || value === null) {
    return [];
  }
  const envelope = Array.isArray(value)
    ? {references: value}
    : value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
  if (envelope === null) {
    return [];
  }
  const schemaRaw =
    envelope.schema_version ?? envelope.schemaVersion ?? envelope.version;
  const schemaVersion =
    schemaRaw === undefined || schemaRaw === null
      ? 1
      : typeof schemaRaw === 'number' && Number.isFinite(schemaRaw)
      ? schemaRaw
      : typeof schemaRaw === 'string'
      ? Number.parseInt(schemaRaw, 10)
      : NaN;
  const forceUnknown = schemaVersion !== 1;
  const rawReferences =
    envelope.references ??
    envelope.evidence_refs ??
    envelope.evidence_references;
  if (!Array.isArray(rawReferences)) {
    return [];
  }
  return rawReferences.slice(0, 24).flatMap(raw => {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      return [];
    }
    const row = raw as Record<string, unknown>;
    const kindRaw = forceUnknown
      ? 'unknown'
      : typeof row.kind === 'string'
      ? row.kind
      : typeof row.type === 'string'
      ? row.type
      : 'unknown';
    const stateRaw = forceUnknown
      ? 'unknown'
      : typeof row.state === 'string'
      ? row.state
      : typeof row.status === 'string'
      ? row.status
      : 'unknown';
    const title = typeof row.title === 'string' ? row.title : undefined;
    const summary =
      typeof row.summary === 'string'
        ? row.summary
        : typeof row.preview === 'string'
        ? row.preview
        : undefined;
    return [
      {
        kind: kindRaw.trim().toLowerCase(),
        state: stateRaw.trim().toLowerCase(),
        ...(title === undefined ? {} : {title}),
        ...(summary === undefined ? {} : {summary}),
      },
    ];
  });
}

function parseOmiChatEvidence(
  row: Record<string, unknown>,
  hasMemories: boolean,
): {title: string; detail: string}[] {
  try {
    const direct =
      row.evidence ??
      row.evidence_envelope ??
      row.evidence_refs ??
      row.evidence_references;
    let refs = parseOmiChatEvidenceRaw(direct);
    if (refs.length === 0 && typeof row.metadata === 'string') {
      try {
        const decoded: unknown = JSON.parse(row.metadata);
        if (
          decoded !== null &&
          typeof decoded === 'object' &&
          !Array.isArray(decoded)
        ) {
          const metadata = decoded as Record<string, unknown>;
          refs = parseOmiChatEvidenceRaw(
            metadata.evidence ??
              metadata.evidence_envelope ??
              metadata.evidence_refs ??
              metadata.evidence_references,
          );
        }
      } catch {
        refs = [];
      }
    }
    if (hasMemories) {
      refs = refs.filter(item => !conversationEvidenceKinds.has(item.kind));
    }
    return refs.map(chatEvidenceCopy);
  } catch {
    return [];
  }
}

function parseOmiChatAppId(row: Record<string, unknown>): string | undefined {
  const raw = row.plugin_id ?? row.app_id;
  if (typeof raw !== 'string') {
    return undefined;
  }
  const id = visibleDisplayText(raw);
  return id === '' ? undefined : id;
}

function wireString(
  row: Record<string, unknown>,
  camel: string,
  snake?: string,
): string | undefined {
  const value = row[camel] ?? (snake === undefined ? undefined : row[snake]);
  if (typeof value !== 'string') {
    return undefined;
  }
  return value.trim() === '' ? undefined : value;
}

function contentBlockChrome(
  eyebrow: string,
  title?: string,
  detail?: string,
): {eyebrow: string; title?: string; detail?: string} {
  const visibleTitle = title === undefined ? '' : visibleDisplayText(title);
  const visibleDetail = detail === undefined ? '' : visibleDisplayText(detail);
  return {
    eyebrow,
    ...(visibleTitle === '' ? {} : {title: visibleTitle}),
    ...(visibleDetail === '' ? {} : {detail: visibleDetail}),
  };
}

function labelledFallback(
  label: string,
  details: (string | undefined)[],
): string {
  const unique: string[] = [];
  for (const detail of details) {
    if (detail === undefined || unique.includes(detail)) {
      continue;
    }
    unique.push(detail);
  }
  return unique.length === 0 ? label : `${label} - ${unique.join(' - ')}`;
}

function contentBlockFallbackLine(raw: unknown): string | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }
  const row = raw as Record<string, unknown>;
  const type = wireString(row, 'type');
  if (type === undefined) {
    return null;
  }
  switch (type) {
    case 'text': {
      const text = wireString(row, 'text');
      return text === undefined ? 'Message' : text;
    }
    case 'toolCall':
    case 'tool_call':
      return labelledFallback('Tool', [
        wireString(row, 'name'),
        wireString(row, 'output'),
        wireString(row, 'inputSummary', 'input_summary'),
      ]);
    case 'thinking':
      return labelledFallback('Thinking', [wireString(row, 'text')]);
    case 'citation':
      return labelledFallback('Source', [
        wireString(row, 'title'),
        wireString(row, 'preview'),
      ]);
    case 'discoveryCard':
    case 'discovery_card':
      return labelledFallback('Discovery', [
        wireString(row, 'title'),
        wireString(row, 'summary'),
      ]);
    case 'questionCard':
    case 'question_card': {
      const text = wireString(row, 'text');
      return text === undefined ? 'Question' : text;
    }
    case 'taskCard':
    case 'task_card':
      return 'Task';
    case 'goalLink':
    case 'goal_link':
      return labelledFallback('Goal', [wireString(row, 'summary')]);
    case 'memoryLink':
    case 'memory_link':
      return labelledFallback('Memory', [wireString(row, 'summary')]);
    case 'captureLink':
    case 'capture_link':
      return labelledFallback('Capture', [wireString(row, 'summary')]);
    case 'conversationLink':
    case 'conversation_link':
      return labelledFallback('Meeting notes ready', [
        wireString(row, 'summary'),
      ]);
    case 'agentSpawn':
    case 'agent_spawn':
      return labelledFallback('Agent started', [
        wireString(row, 'title'),
        wireString(row, 'objective'),
      ]);
    case 'agentCompletion':
    case 'agent_completion':
      return labelledFallback('Agent completed', [
        wireString(row, 'title'),
        wireString(row, 'output'),
      ]);
    case 'memoryReviewCard':
    case 'memory_review_card':
    case 'followUp':
    case 'follow_up':
    case 'evidence':
    case 'evidence_envelope':
      return null;
    default:
      return labelledFallback('Chat item', [
        wireString(row, 'title'),
        wireString(row, 'summary'),
        wireString(row, 'text'),
      ]);
  }
}

function memoryReviewCategoryLabel(
  category: string | undefined,
): string | undefined {
  if (category === undefined) {
    return undefined;
  }
  const normalized = visibleDisplayText(category).replace(/_/g, ' ');
  if (normalized === '') {
    return undefined;
  }
  return normalized[0].toUpperCase() + normalized.slice(1);
}

function parseMemoryReviewItems(
  value: unknown,
): {eyebrow: string; title?: string; detail?: string}[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows: {eyebrow: string; title?: string; detail?: string}[] = [];
  for (const entry of value) {
    if (rows.length === 3) {
      break;
    }
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      continue;
    }
    const item = entry as Record<string, unknown>;
    const memoryId = wireString(item, 'memoryId', 'memory_id');
    const content = wireString(item, 'content');
    if (memoryId === undefined || content === undefined) {
      continue;
    }
    rows.push(
      contentBlockChrome(
        'Things I learned today',
        content,
        memoryReviewCategoryLabel(wireString(item, 'category')),
      ),
    );
  }
  return rows;
}

function agentCompletionEyebrow(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (
    normalized === 'completed' ||
    normalized === 'succeeded' ||
    normalized === 'success'
  ) {
    return 'Completed';
  }
  if (
    normalized === 'cancelled' ||
    normalized === 'canceled' ||
    normalized === 'stopped'
  ) {
    return 'Cancelled';
  }
  if (
    normalized === 'timed_out' ||
    normalized === 'timedout' ||
    normalized === 'timeout'
  ) {
    return 'Timed out';
  }
  return 'Failed';
}

function parseQuestionSelectedLabel(
  row: Record<string, unknown>,
): string | undefined {
  const selectedId = wireString(row, 'selectedOptionId', 'selected_option_id');
  if (selectedId === undefined) {
    return undefined;
  }
  const rawOptions = row.options;
  if (!Array.isArray(rawOptions)) {
    return undefined;
  }
  for (const entry of rawOptions) {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      continue;
    }
    const option = entry as Record<string, unknown>;
    const optionId = wireString(option, 'optionId', 'option_id');
    if (optionId !== selectedId) {
      continue;
    }
    return wireString(option, 'label');
  }
  return undefined;
}

function parseQuestionOptionLabels(
  row: Record<string, unknown>,
): string | undefined {
  const selectedId = wireString(row, 'selectedOptionId', 'selected_option_id');
  if (selectedId !== undefined) {
    return parseQuestionSelectedLabel(row);
  }
  const rawOptions = row.options;
  if (!Array.isArray(rawOptions)) {
    return undefined;
  }
  const labels: string[] = [];
  for (const entry of rawOptions.slice(0, 20)) {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      continue;
    }
    const option = entry as Record<string, unknown>;
    if (wireString(option, 'optionId', 'option_id') === undefined) {
      continue;
    }
    const label = wireString(option, 'label');
    if (label === undefined) {
      continue;
    }
    const visible = visibleDisplayText(label);
    if (visible === '') {
      continue;
    }
    labels.push(visible);
  }
  return labels.length === 0 ? undefined : labels.join(' · ');
}

function questionHasOptions(row: Record<string, unknown>): boolean {
  const rawOptions = row.options;
  if (!Array.isArray(rawOptions)) {
    return false;
  }
  return rawOptions.some(entry => {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      return false;
    }
    const option = entry as Record<string, unknown>;
    return (
      wireString(option, 'optionId', 'option_id') !== undefined &&
      wireString(option, 'label') !== undefined
    );
  });
}

function parseContentBlock(
  raw: unknown,
): {eyebrow: string; title?: string; detail?: string; taskId?: string}[] {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return [];
  }
  const row = raw as Record<string, unknown>;
  const type = wireString(row, 'type');
  if (type === 'followUp' || type === 'follow_up') {
    const text = wireString(row, 'text');
    if (text === undefined) {
      return [];
    }
    return [contentBlockChrome(visibleDisplayText(text))];
  }
  const id = wireString(row, 'id');
  if (type === undefined || id === undefined) {
    return [];
  }
  switch (type) {
    case 'discoveryCard':
    case 'discovery_card':
      return [
        contentBlockChrome(
          'Discovery',
          wireString(row, 'title'),
          wireString(row, 'summary'),
        ),
      ];
    case 'questionCard':
    case 'question_card': {
      const text = wireString(row, 'text');
      const subject = row.subject;
      if (
        wireString(row, 'questionId', 'question_id') === undefined ||
        text === undefined ||
        subject === null ||
        typeof subject !== 'object' ||
        Array.isArray(subject)
      ) {
        return [];
      }
      const subjectRow = subject as Record<string, unknown>;
      if (
        wireString(subjectRow, 'kind') === undefined ||
        wireString(subjectRow, 'id') === undefined ||
        !questionHasOptions(row)
      ) {
        return [];
      }
      return [
        contentBlockChrome('Question', text, parseQuestionOptionLabels(row)),
      ];
    }
    case 'taskCard':
    case 'task_card': {
      const taskId = wireString(row, 'taskId', 'task_id');
      if (taskId === undefined) {
        return [];
      }
      return [{...contentBlockChrome('Task'), taskId}];
    }
    case 'goalLink':
    case 'goal_link': {
      const summary = wireString(row, 'summary');
      if (
        wireString(row, 'goalId', 'goal_id') === undefined ||
        summary === undefined
      ) {
        return [];
      }
      return [contentBlockChrome('Goal', summary)];
    }
    case 'memoryLink':
    case 'memory_link': {
      const summary = wireString(row, 'summary');
      if (
        wireString(row, 'memoryId', 'memory_id') === undefined ||
        summary === undefined
      ) {
        return [];
      }
      return [contentBlockChrome('Memory', summary)];
    }
    case 'captureLink':
    case 'capture_link': {
      const summary = wireString(row, 'summary');
      if (
        wireString(row, 'conversationId', 'conversation_id') === undefined ||
        summary === undefined
      ) {
        return [];
      }
      return [contentBlockChrome('Conversation', summary)];
    }
    case 'conversationLink':
    case 'conversation_link': {
      const summary = wireString(row, 'summary');
      if (
        wireString(row, 'conversationId', 'conversation_id') === undefined ||
        summary === undefined
      ) {
        return [];
      }
      const rows = [contentBlockChrome('Conversation', summary)];
      const rawItems =
        row.recommendedActionItems ?? row.recommended_action_items;
      if (!Array.isArray(rawItems)) {
        return rows;
      }
      for (const entry of rawItems.slice(0, 20)) {
        if (
          entry === null ||
          typeof entry !== 'object' ||
          Array.isArray(entry)
        ) {
          continue;
        }
        const description = wireString(
          entry as Record<string, unknown>,
          'description',
        );
        if (description === undefined) {
          continue;
        }
        rows.push(contentBlockChrome('Recommended next steps', description));
      }
      return rows;
    }
    case 'agentSpawn':
    case 'agent_spawn': {
      if (
        wireString(row, 'sessionId', 'session_id') === undefined ||
        wireString(row, 'runId', 'run_id') === undefined
      ) {
        return [];
      }
      return [
        contentBlockChrome(
          'Processing',
          wireString(row, 'title') ?? '',
          wireString(row, 'objective') ?? '',
        ),
      ];
    }
    case 'agentCompletion':
    case 'agent_completion':
      return [
        contentBlockChrome(
          agentCompletionEyebrow(wireString(row, 'status') ?? 'completed'),
          wireString(row, 'title') ?? '',
          wireString(row, 'output') ?? '',
        ),
      ];
    case 'memoryReviewCard':
    case 'memory_review_card':
      return parseMemoryReviewItems(row.items);
    default:
      return [];
  }
}

function parseContentBlocksList(value: unknown): unknown[] | null {
  if (typeof value === 'string') {
    try {
      const decoded: unknown = JSON.parse(value);
      return Array.isArray(decoded) ? decoded : null;
    } catch {
      return null;
    }
  }
  return Array.isArray(value) ? value : null;
}

function parseOmiChatContentBlocksRaw(
  row: Record<string, unknown>,
): unknown[] | null {
  try {
    let raw = parseContentBlocksList(row.content_blocks);
    if (raw === null && typeof row.metadata === 'string') {
      try {
        const decoded: unknown = JSON.parse(row.metadata);
        if (
          decoded !== null &&
          typeof decoded === 'object' &&
          !Array.isArray(decoded)
        ) {
          raw = parseContentBlocksList(
            (decoded as Record<string, unknown>).content_blocks,
          );
        }
      } catch {
        raw = null;
      }
    }
    return raw;
  } catch {
    return null;
  }
}

function parseOmiChatContentBlocks(
  row: Record<string, unknown>,
): {eyebrow: string; title?: string; detail?: string; taskId?: string}[] {
  try {
    const raw = parseOmiChatContentBlocksRaw(row);
    if (raw === null) {
      return [];
    }
    return raw.slice(0, 24).flatMap(parseContentBlock);
  } catch {
    return [];
  }
}

function parseOmiChatFallbackText(row: Record<string, unknown>): string {
  try {
    const raw = parseOmiChatContentBlocksRaw(row);
    if (raw === null) {
      return '';
    }
    return raw
      .slice(0, 24)
      .flatMap(block => {
        if (parseContentBlock(block).length > 0) {
          return [];
        }
        const line = contentBlockFallbackLine(block);
        return line === null || line === '' ? [] : [line];
      })
      .join('\n');
  } catch {
    return '';
  }
}

export function parseOmiMessage(value: unknown): ChatMessage {
  const row = object(value);
  const createdAt =
    typeof row.created_at === 'string' ? Date.parse(row.created_at) : NaN;
  if (
    typeof row.id !== 'string' ||
    row.id.length === 0 ||
    typeof row.text !== 'string' ||
    (row.sender !== 'human' && row.sender !== 'ai') ||
    !Number.isFinite(createdAt)
  ) {
    throw new Error('Omi chat message is malformed');
  }
  const memories = parseOmiChatMemories(row.memories);
  const attachments = parseOmiChatFiles(row.files, row.files_id);
  const chart = parseOmiChatChart(row.chart_data);
  const evidence = parseOmiChatEvidence(row, memories.length > 0);
  const contentBlocks = parseOmiChatContentBlocks(row);
  const appId = parseOmiChatAppId(row);
  const fallbackText =
    visibleDisplayText(row.text) === '' ? parseOmiChatFallbackText(row) : '';
  return {
    id: row.id,
    text: fallbackText === '' ? row.text : fallbackText,
    sender: row.sender,
    ...(row.type === 'day_summary' ? {type: 'day_summary' as const} : {}),
    createdAt,
    generationOutcome: null,
    ...(memories.length === 0 ? {} : {memories}),
    ...(attachments.length === 0 ? {} : {attachments}),
    ...(chart === undefined ? {} : {chart}),
    ...(evidence.length === 0 ? {} : {evidence}),
    ...(contentBlocks.length === 0 ? {} : {contentBlocks}),
    ...(appId === undefined ? {} : {appId}),
  };
}

export function omiHistoryOffset(cursor: string): number {
  if (!/^omi-offset:[0-9]+$/.test(cursor)) {
    throw new Error('Omi chat cursor is malformed');
  }
  const offset = Number(cursor.slice('omi-offset:'.length));
  if (!Number.isSafeInteger(offset)) {
    throw new Error('Omi chat cursor is malformed');
  }
  return offset;
}

export function parseOmiHistory(
  body: string | null,
  offset: number,
): ChatHistoryPage {
  const rows: unknown = JSON.parse(body ?? 'null');
  if (!Array.isArray(rows) || rows.length > 50) {
    throw new Error('Omi chat history is malformed');
  }
  return {
    messages: rows.map(parseOmiMessage).reverse(),
    hasOlder: rows.length === 50,
    olderCursor:
      rows.length === 50 ? `omi-offset:${offset + rows.length}` : null,
  };
}

export function parseOmiChatStream(body: string | null): ChatMessage {
  if (body === null || body.length > 4_000_000) {
    throw new Error('Omi chat stream is malformed');
  }
  for (const frame of body.split(/\r?\n\r?\n/).reverse()) {
    if (!frame.startsWith('done: ')) continue;
    const bytes = decodeBase64(frame.slice(6).trim());
    const encoded = Array.from(
      bytes,
      byte => `%${byte.toString(16).padStart(2, '0')}`,
    ).join('');
    const message = parseOmiMessage(JSON.parse(decodeURIComponent(encoded)));
    if (message.sender !== 'ai')
      throw new Error('Omi chat terminal sender is invalid');
    return message;
  }
  throw new Error('Omi chat ended without a terminal message');
}
