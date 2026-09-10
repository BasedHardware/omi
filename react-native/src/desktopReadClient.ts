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
  emoji?: string;
  photoCount?: number;
  category?: string;
};

export function visibleDisplayText(value: string): string {
  return value.replace(/^[\s\u0085]+|[\s\u0085]+$/gu, '');
}

export function conversationDisplayTitle(item: {
  title: string;
  status: string;
}): string {
  const title = visibleDisplayText(item.title);
  if (title !== '') {
    return title;
  }
  return item.status === 'processing'
    ? 'Processing conversation…'
    : 'Conversation title unavailable';
}

function conversationListUsesListenExcerpt(id: string | undefined): boolean {
  if (id === undefined || id.startsWith('chat:')) {
    return false;
  }
  if (id.startsWith('recording:')) {
    return id.length > 'recording:'.length;
  }
  return true;
}

export function conversationListUsesListenOverview(item: {
  id?: string;
  title: string;
  summary: string;
}): boolean {
  const title = visibleDisplayText(item.title);
  const summary = visibleDisplayText(item.summary);
  return (
    conversationListUsesListenExcerpt(item.id) &&
    title !== '' &&
    summary !== '' &&
    summary.startsWith(title)
  );
}

export function conversationRecapTitle(item: {
  id?: string;
  title: string;
  summary: string;
  status: string;
}): string {
  const title = visibleDisplayText(item.title);
  const summary = visibleDisplayText(item.summary);
  if (conversationListUsesListenOverview(item)) {
    return summary;
  }
  if (title !== '') {
    return title;
  }
  if (summary !== '') {
    return summary;
  }
  return conversationDisplayTitle(item);
}

export function conversationDisplaySummary(item: {
  summary: string;
  status: string;
}): string {
  const summary = visibleDisplayText(item.summary);
  if (summary !== '') {
    return summary;
  }
  return item.status === 'processing'
    ? 'Conversation summary is not ready yet.'
    : 'Conversation summary unavailable';
}

export function conversationStatusCopy(status: string): string {
  const trimmed = visibleDisplayText(status);
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

export function conversationListStatusCopy(status: string): string | null {
  const trimmed = visibleDisplayText(status);
  if (trimmed === 'failed') {
    return 'Failed';
  }
  if (trimmed === 'processing' || trimmed === 'merging') {
    return 'Processing';
  }
  return null;
}

export function recordingTranscriptSpeakerCopy(segment: {
  isUser?: boolean;
  speaker?: string | number | null;
}): string | null {
  if (segment.isUser === true) {
    return 'You';
  }
  if (
    typeof segment.speaker === 'number' &&
    Number.isSafeInteger(segment.speaker) &&
    segment.speaker >= 0
  ) {
    return `Speaker ${segment.speaker + 1}`;
  }
  if (typeof segment.speaker !== 'string') {
    return null;
  }
  const trimmed = visibleDisplayText(segment.speaker);
  if (trimmed === '') {
    return null;
  }
  const labeled = /^SPEAKER_(\d+)$/.exec(trimmed);
  return labeled !== null ? `Speaker ${Number(labeled[1]) + 1}` : trimmed;
}

export function recordingTranscriptCanDisplaySeconds(
  segments: readonly {start: number | null; end: number | null}[],
): boolean {
  if (segments.length === 0) {
    return false;
  }
  const windows: {start: number; end: number}[] = [];
  for (const segment of segments) {
    if (typeof segment.start !== 'number' || typeof segment.end !== 'number') {
      return false;
    }
    windows.push({start: segment.start, end: segment.end});
  }
  return legacyTranscriptCanDisplaySeconds(windows);
}

export function legacyTranscriptCanDisplaySeconds(
  segments: readonly {start: number; end: number}[],
): boolean {
  for (let i = 0; i < segments.length; i += 1) {
    for (let j = i + 1; j < segments.length; j += 1) {
      if (
        segments[i].start > segments[j].end ||
        segments[i].end > segments[j].start
      ) {
        return false;
      }
    }
  }
  return true;
}

function legacyTranscriptClockPart(totalSeconds: number): string {
  const seconds = Math.trunc(totalSeconds);
  const hours = Math.trunc(seconds / 3600);
  const minutes = Math.trunc(seconds / 60) % 60;
  const remainder = seconds % 60;
  const pad = (value: number) => String(Math.abs(value)).padStart(2, '0');
  return `${pad(hours)}:${pad(minutes)}:${pad(remainder)}`;
}

export function legacyTranscriptTimestampCopy(
  start: number,
  end: number,
): string {
  return `${legacyTranscriptClockPart(start)} - ${legacyTranscriptClockPart(
    end,
  )}`;
}

export function conversationListEmoji(item: {
  discarded: boolean;
  emoji?: string | null;
}): string | null {
  if (item.discarded) {
    return null;
  }
  const emoji = visibleDisplayText(item.emoji ?? '');
  return emoji === '' ? null : emoji;
}

export function conversationListCategory(item: {
  discarded: boolean;
  category?: string | null;
}): string | null {
  if (item.discarded) {
    return null;
  }
  const category = visibleDisplayText(item.category ?? '');
  if (category === '') {
    return null;
  }
  return category.charAt(0).toUpperCase() + category.slice(1);
}

export function conversationListSourceTag(item: {
  source?: string | null;
}): string | null {
  const source = visibleDisplayText(item.source ?? '');
  if (source === 'screenpipe') {
    return 'Screenpipe';
  }
  if (source === 'openglass') {
    return 'OmiGlass';
  }
  if (source === 'sdcard') {
    return 'SD Card';
  }
  if (source === 'rayban_meta') {
    return 'Ray-Ban Meta';
  }
  return null;
}

export function conversationListTag(item: {
  discarded: boolean;
  category?: string | null;
  source?: string | null;
}): string | null {
  return conversationListSourceTag(item) ?? conversationListCategory(item);
}

export function conversationVisibilityCopy(
  visibility: string | null | undefined,
): string | null {
  const value = visibleDisplayText(visibility ?? '');
  if (value === 'shared') {
    return 'Shared';
  }
  if (value === 'public') {
    return 'Public';
  }
  return null;
}

export function conversationDiscardedPhotoCopy(item: {
  discarded: boolean;
  photoCount?: number;
}): string | null {
  if (!item.discarded) {
    return null;
  }
  const count = item.photoCount;
  if (typeof count !== 'number' || !Number.isSafeInteger(count) || count <= 0) {
    return null;
  }
  return `${count} photos`;
}

export function conversationHasFinishClock(conversation: {
  finishedAt: string | null;
  status: string;
}): boolean {
  if (conversation.finishedAt !== null) {
    return true;
  }
  const status = visibleDisplayText(conversation.status);
  return status === 'completed' || status === 'failed';
}

export function formatConversationDuration(
  startedAt: string | null,
  finishedAt: string | null,
): string {
  if (startedAt === null || finishedAt === null) {
    return 'Duration unavailable';
  }
  const startedAtMs = Date.parse(startedAt);
  const finishedAtMs = Date.parse(finishedAt);
  if (
    !Number.isFinite(startedAtMs) ||
    startedAtMs <= 0 ||
    !Number.isFinite(finishedAtMs) ||
    finishedAtMs <= 0
  ) {
    return 'Duration unavailable';
  }
  const duration = finishedAtMs - startedAtMs;
  if (duration < 0) {
    return 'Duration unavailable';
  }
  if (duration < 60_000) {
    return '< 1 min';
  }
  const minutes = Math.round(duration / 60_000);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes === 0
    ? `${hours} hr`
    : `${hours} hr ${remainingMinutes} min`;
}

export function conversationTranscriptDurationCopy(
  segments: readonly {end: number}[] | null | undefined,
): string | null {
  if (segments == null || segments.length === 0) {
    return null;
  }
  let lastEnd = 0;
  for (const segment of segments) {
    if (
      typeof segment.end === 'number' &&
      Number.isFinite(segment.end) &&
      segment.end > lastEnd
    ) {
      lastEnd = segment.end;
    }
  }
  const seconds = Math.trunc(lastEnd);
  if (seconds <= 0) {
    return null;
  }
  if (seconds < 60) {
    return `${seconds} secs`;
  }
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    if (remainingSeconds === 0) {
      return minutes === 1 ? `${minutes} min` : `${minutes} mins`;
    }
    return `${minutes} mins ${remainingSeconds} secs`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const remainingMinutes = Math.floor((seconds % 3600) / 60);
    if (remainingMinutes === 0) {
      return hours === 1 ? `${hours} hour` : `${hours} hours`;
    }
    return `${hours} hours ${remainingMinutes} mins`;
  }
  const days = Math.floor(seconds / 86400);
  const remainingHours = Math.floor((seconds % 86400) / 3600);
  if (remainingHours === 0) {
    return days === 1 ? `${days} day` : `${days} days`;
  }
  return `${days} days ${remainingHours} hours`;
}

export function accountWireCopy(value: string, unavailable: string): string {
  const trimmed = visibleDisplayText(value);
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
  const trimmed = visibleDisplayText(value ?? '');
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
      .map(part => visibleDisplayText(part))
      .filter(part => part !== '')
      .join(' · ') || 'Identity unavailable for this connection.'
  );
}

export function subscriptionPlanCopy(plan: string): string {
  return accountWireCopy(plan, 'Plan unavailable');
}

export function usageStatsCopy(
  stats:
    | {
        transcriptionSeconds: number;
        wordsTranscribed: number;
        insightsGained: number;
        memoriesCreated: number;
      }
    | null
    | undefined,
): {title: string; copy: string}[] | null {
  if (stats == null) {
    return null;
  }
  if (
    stats.transcriptionSeconds === 0 &&
    stats.wordsTranscribed === 0 &&
    stats.insightsGained === 0 &&
    stats.memoriesCreated === 0
  ) {
    return null;
  }
  return [
    {
      title: 'Listening',
      copy: `${Math.round(stats.transcriptionSeconds / 60)} minutes`,
    },
    {
      title: 'Understanding',
      copy: `${stats.wordsTranscribed} words`,
    },
    {
      title: 'Providing',
      copy: `${stats.insightsGained} insights`,
    },
    {
      title: 'Remembering',
      copy: `${stats.memoriesCreated} memories`,
    },
  ];
}

export function primaryLanguageCopy(
  code: string | null | undefined,
  names:
    | ReadonlyArray<{code: string; name: string}>
    | null
    | undefined,
): string | null {
  const language = visibleDisplayText(code ?? '');
  if (language === '') {
    return null;
  }
  const name = names?.find(item => item.code === language)?.name;
  const visibleName = visibleDisplayText(name ?? '');
  return visibleName === '' ? language : visibleName;
}

export function peopleNameRows(
  names: Map<string, string>,
): {id: string; name: string}[] {
  return Array.from(names, ([id, name]) => ({id, name}));
}

function fairUseStageCopy(stage: string): string | null {
  if (stage === 'warning') {
    return 'Warning';
  }
  if (stage === 'throttle') {
    return 'Throttled';
  }
  if (stage === 'restrict') {
    return 'Restricted';
  }
  return null;
}

function fairUseHoursCopy(hours: number, limit: number): string {
  return `${hours.toFixed(1)}h / ${limit.toFixed(0)}h`;
}

export function fairUseCopy(
  status:
    | {
        stage: string;
        caseRef: string;
        message: string;
        speechHoursToday: number;
        speechHours3day: number;
        speechHoursWeekly: number;
        dailyHours: number;
        threeDayHours: number;
        weeklyHours: number;
        dailyLimitMs: number;
        usedMs: number;
        exhausted: boolean;
      }
    | null
    | undefined,
): {title: string; copy: string}[] | null {
  if (status == null) {
    return null;
  }
  const rows: {title: string; copy: string}[] = [];
  const stage = fairUseStageCopy(status.stage);
  if (stage !== null) {
    const caseRef = visibleDisplayText(status.caseRef);
    rows.push({
      title: 'Fair Use',
      copy: caseRef === '' ? stage : `${stage} · ${caseRef}`,
    });
  }
  rows.push(
    {
      title: 'Today',
      copy: fairUseHoursCopy(status.speechHoursToday, status.dailyHours),
    },
    {
      title: '3-Day Rolling',
      copy: fairUseHoursCopy(status.speechHours3day, status.threeDayHours),
    },
    {
      title: 'Weekly Rolling',
      copy: fairUseHoursCopy(status.speechHoursWeekly, status.weeklyHours),
    },
  );
  const message = visibleDisplayText(status.message);
  if (message !== '') {
    rows.push({title: 'Fair Use', copy: message});
  }
  if (status.stage === 'restrict' && status.dailyLimitMs > 0) {
    rows.push({
      title: 'Daily transcription',
      copy: `${Math.round(status.usedMs / 60000)}m / ${Math.round(
        status.dailyLimitMs / 60000,
      )}m`,
    });
    if (status.exhausted) {
      rows.push({
        title: 'Daily transcription',
        copy: 'Daily transcription limit reached',
      });
    }
  }
  return rows;
}

function dottedVersionParts(value: string): number[] | null {
  const parts = visibleDisplayText(value).split('.');
  if (parts.length === 0 || parts.some(part => part === '' || !/^[0-9]+$/.test(part))) {
    return null;
  }
  return parts.map(part => Number(part));
}

function compareDottedVersion(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const a = left[index] ?? 0;
    const b = right[index] ?? 0;
    if (a !== b) {
      return a < b ? -1 : 1;
    }
  }
  return 0;
}

export function firmwareUpdateCopy(
  currentFirmware: string,
  details: {version: string; draft: boolean; minVersion: string | null} | null,
): {latest: string; available: boolean} | null {
  if (details === null || details.draft) {
    return null;
  }
  const latest = visibleDisplayText(details.version);
  if (latest === '') {
    return null;
  }
  const current = dottedVersionParts(currentFirmware);
  const newest = dottedVersionParts(latest);
  const minimum =
    details.minVersion === null ? null : dottedVersionParts(details.minVersion);
  const available =
    current !== null &&
    newest !== null &&
    (minimum === null || compareDottedVersion(current, minimum) >= 0) &&
    compareDottedVersion(newest, current) > 0;
  return {latest, available};
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
  const url = visibleDisplayText(webhook.url ?? '');
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
  const author = visibleDisplayText(app.author);
  if (author !== '') {
    return author;
  }
  const category = appCategoryCopy(app.category);
  if (category !== '') {
    return category;
  }
  const description = visibleDisplayText(app.description);
  return description !== '' ? description : 'App details unavailable';
}

export function appDisplayAttribution(app: {
  author: string;
  category: string;
}): string {
  return [appCategoryCopy(app.category), visibleDisplayText(app.author)]
    .filter(part => part !== '')
    .join(' · ');
}

export function appImageUrl(image: string | null | undefined): string | null {
  const trimmed = visibleDisplayText(image ?? '');
  if (!/^https?:\/\//i.test(trimmed)) {
    return null;
  }
  return trimmed;
}

export function appRatingCopy(
  ratingAvg: number | null | undefined,
  ratingCount: number | null | undefined,
): string | null {
  if (
    ratingAvg === undefined ||
    ratingAvg === null ||
    !Number.isFinite(ratingAvg)
  ) {
    return null;
  }
  const rating = ratingAvg.toFixed(1);
  if (
    ratingCount === undefined ||
    ratingCount === null ||
    !Number.isSafeInteger(ratingCount) ||
    ratingCount < 0
  ) {
    return rating;
  }
  return `${rating} (${ratingCount})`;
}

export function chatAttachmentDisplayName(name: string): string {
  return accountFieldCopy(name, 'Attachment name unavailable');
}

const CHAT_ATTACHMENT_MEDIA_COPY: Readonly<Record<string, string>> = {
  'application/pdf': 'PDF',
  'image/gif': 'GIF',
  'image/jpeg': 'JPEG',
  'image/png': 'PNG',
  'image/webp': 'WebP',
  'text/markdown': 'Markdown',
  'text/plain': 'Text',
};

export function chatAttachmentMediaCopy(mediaType: string | undefined): string {
  if (mediaType === undefined) {
    return '';
  }
  const trimmed = visibleDisplayText(mediaType);
  return trimmed === '' ? '' : CHAT_ATTACHMENT_MEDIA_COPY[trimmed] ?? '';
}

export function chatAttachmentSizeCopy(sizeBytes: number | undefined): string {
  if (sizeBytes === undefined) {
    return '';
  }
  if (!Number.isSafeInteger(sizeBytes) || sizeBytes < 1) {
    return 'Size unavailable';
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    const kb = sizeBytes / 1024;
    return Number.isInteger(kb) ? `${kb} KB` : `${kb.toFixed(1)} KB`;
  }
  const mb = sizeBytes / (1024 * 1024);
  return Number.isInteger(mb) ? `${mb} MB` : `${mb.toFixed(1)} MB`;
}

export function chatAttachmentCopy(attachment: {
  displayName: string;
  mediaType?: string;
  sizeBytes?: number;
}): string {
  return [
    chatAttachmentDisplayName(attachment.displayName),
    chatAttachmentMediaCopy(attachment.mediaType),
    chatAttachmentSizeCopy(attachment.sizeBytes),
  ]
    .filter(part => part !== '')
    .join(' · ');
}

export function chatChartCopy(chart: {
  title: string;
  points: readonly {label: string; value: number}[];
}): string | null {
  const title = visibleDisplayText(chart.title);
  const lines = chart.points.flatMap(point => {
    const label = visibleDisplayText(point.label);
    if (label === '' || !Number.isFinite(point.value)) {
      return [];
    }
    return [`${label} · ${point.value}`];
  });
  if (lines.length === 0) {
    return null;
  }
  return title === '' ? lines.join('\n') : `${title}\n${lines.join('\n')}`;
}

export function chatMessageDisplayText(
  message: {
    text: string;
    generationOutcome: 'completed' | 'cancelled' | 'failed' | null;
    generationRetryable?: boolean;
    attachments?: readonly {
      displayName: string;
      mediaType?: string;
      sizeBytes?: number;
    }[];
    chart?: {
      title: string;
      points: readonly {label: string; value: number}[];
    };
  },
  cancelledEmptyCopy = 'Response stopped',
): string {
  if (message.generationOutcome === 'failed') {
    return message.generationRetryable === true
      ? 'Response failed. Try again.'
      : 'Response failed.';
  }
  const text = visibleDisplayText(message.text);
  const chartCopy =
    message.chart === undefined ? null : chatChartCopy(message.chart);
  const extraLines = [
    ...(message.attachments ?? []).map(attachment =>
      chatAttachmentCopy(attachment),
    ),
    ...(chartCopy === null ? [] : [chartCopy]),
  ];
  if (text !== '') {
    return extraLines.length > 0 ? `${text}\n${extraLines.join('\n')}` : text;
  }
  if (message.generationOutcome === 'cancelled') {
    return cancelledEmptyCopy;
  }
  if (extraLines.length > 0) {
    return extraLines.join('\n');
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

export function chatDaySummaryCopy(
  type: 'text' | 'day_summary' | 'unknown' | undefined,
): string {
  return type === 'day_summary' ? 'Day Summary' : '';
}

export function chatMemoryCitationCopy(memory: {
  title: string;
  emoji?: string | null;
}): string | null {
  const title = visibleDisplayText(memory.title);
  if (title === '') {
    return null;
  }
  const emoji = visibleDisplayText(memory.emoji ?? '');
  return emoji === '' ? title : `${emoji} ${title}`;
}

export function chatEvidenceKindCopy(kind: string): string {
  switch (kind) {
    case 'conversation_summary':
      return 'Conversation summary';
    case 'conversation_segment':
      return 'Conversation segment';
    case 'screen':
      return 'Current screen';
    case 'keyframe':
      return 'Screen keyframe';
    case 'request':
      return 'Evidence request';
    default:
      return 'Evidence';
  }
}

export function chatEvidenceStateCopy(state: string): string {
  switch (state) {
    case 'available':
      return 'Available';
    case 'loading':
      return 'Loading';
    case 'offline':
      return 'Unavailable offline';
    case 'pruned':
      return 'No longer available';
    case 'failed':
      return 'Failed to load';
    default:
      return 'Unavailable';
  }
}

export function chatEvidenceCopy(item: {
  kind: string;
  state: string;
  title?: string;
  summary?: string;
}): {title: string; detail: string} {
  const title = visibleDisplayText(item.title ?? '');
  const summary = visibleDisplayText(item.summary ?? '');
  return {
    title: title === '' ? chatEvidenceKindCopy(item.kind) : title,
    detail: summary === '' ? chatEvidenceStateCopy(item.state) : summary,
  };
}

export function memoryDisplayTitle(item: {
  title: string;
  summary: string;
}): string {
  const title = visibleDisplayText(item.title);
  const summary = visibleDisplayText(item.summary);
  return visibleMemoryText(title !== '' ? title : summary);
}

export function memoryDisplayBody(item: {
  title: string;
  summary: string;
}): string {
  const title = visibleDisplayText(item.title);
  const summary = visibleDisplayText(item.summary);
  return visibleMemoryText(summary !== '' ? summary : title);
}

export function memoryCitationCopy(citations: readonly string[]): string {
  const visible = citations.filter(id => visibleDisplayText(id) !== '');
  return visible.length === 1 ? '1 citation' : `${visible.length} citations`;
}

export function memorySynthesisCopy(item: {
  provenance: {synthesisVersion: string | null};
}): string | null {
  const version = visibleDisplayText(item.provenance.synthesisVersion ?? '');
  return version !== '' ? 'Synthesized memory' : null;
}

export function memoryLedgerSlotCopy(item: {
  ledgerSlot?: string | null;
}): string | null {
  const slot = visibleDisplayText(item.ledgerSlot ?? '');
  return slot === '' ? null : slot;
}

export function memoryLedgerPlaybookCopy(item: {
  ledgerBody?: string | null;
}): string | null {
  const body = visibleDisplayText(item.ledgerBody ?? '');
  return body === '' ? null : body;
}

export function memoryBaselineCopy(item: {
  isBaseline?: boolean;
}): string | null {
  return item.isBaseline === true ? 'Baseline Memory' : null;
}

export function memoryLockedCopy(item: {locked?: boolean}): string | null {
  return item.locked === true ? 'Locked' : null;
}

export function memoryCaptureDeviceCopy(
  device: string | null | undefined,
): string | null {
  const raw = visibleDisplayText(device ?? '');
  if (raw === '') {
    return null;
  }
  switch (raw.split('_')[0]) {
    case 'macos':
      return 'Mac';
    case 'ios':
      return 'iPhone';
    case 'android':
      return 'Android';
    default:
      return null;
  }
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
    return `Completed · ${formatTaskDue(item.dueAt)}`;
  }
  if (item.dueAt === null || !Number.isFinite(item.dueAt) || item.dueAt <= 0) {
    return formatTaskDue(item.dueAt);
  }
  return `Due ${formatTaskDue(item.dueAt)}`;
}

export function taskDisplayTitle(item: {title: string}): string {
  const title = visibleDisplayText(item.title);
  return title !== '' ? title : 'Task title unavailable';
}

const TASK_EXPORT_PLATFORM_COPY: Record<string, string> = {
  apple_reminders: 'Reminders',
  asana: 'Asana',
  clickup: 'ClickUp',
  google_tasks: 'Google Tasks',
  todoist: 'Todoist',
};

export function taskExportCopy(
  exported: boolean | null | undefined,
  exportPlatform: string | null | undefined,
): string | null {
  if (exported !== true) {
    return null;
  }
  const platform = visibleDisplayText(exportPlatform ?? '');
  if (platform === '') {
    return null;
  }
  return `Exported to ${TASK_EXPORT_PLATFORM_COPY[platform] ?? platform}`;
}

export const TASK_INDENT_STEP = 28;
export const TASK_INDENT_MAX = 3;

export function taskIndentPadding(indentLevel: number): number {
  if (!Number.isFinite(indentLevel) || indentLevel <= 0) {
    return 0;
  }
  return Math.min(Math.trunc(indentLevel), TASK_INDENT_MAX) * TASK_INDENT_STEP;
}

function visibleMemoryText(text: string): string {
  const parsed = parseMemoryText(text);
  const body = visibleDisplayText(parsed.body);
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
  ledgerSlot?: string;
  ledgerBody?: string;
  isBaseline?: boolean;
  captureDeviceLabel?: string;
  locked?: boolean;
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
  exportCopy?: string;
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

export function conversationCaptureCopy(
  capturedAtMs: number | undefined,
  nowEpochMilliseconds: number = Date.now(),
): string | null {
  if (capturedAtMs === undefined) {
    return null;
  }
  const label = clockLabel(capturedAtMs, nowEpochMilliseconds);
  return `Captured (device time) · ${
    label === '' ? 'Time unavailable' : label
  }`;
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
  const normalized = visibleDisplayText(query).toLocaleLowerCase();
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
export class MemoryCursorExpiredError extends Error {}

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
    if (
      response.status === 400 &&
      id === 'desktop-memories-read' &&
      path.includes('&cursor=')
    ) {
      throw new MemoryCursorExpiredError('Memories changed. Refresh the list.');
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
    text.match(/^((?:[a-z0-9_-]+:){2,}[a-z0-9_-]+)[\s\u0085]+(.+)$/is) ??
    text.match(/^([a-z0-9]+(?:-[a-z0-9]+){2,}):[\s\u0085]+(.+)$/is);
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
      apiContract: result.apiContract,
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
      searchableText: memoryDisplayTitle({
        title: parsedText.body,
        summary: parsedText.body,
      }),
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
        ? 'No due date'
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
