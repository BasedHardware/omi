import {isOptionalCaptureTimestamp} from './captureTimestamp';
import {
  conversationDiscardedTranscriptCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationStructuredEmojiCopy,
  conversationStructuredCategoryCopy,
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
  return text(value);
}
function bool(value: unknown, fallback = false): boolean {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'boolean') throw new Error('Omi boolean is malformed');
  return value;
}
function optionalBool(value: unknown): boolean | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'boolean') throw new Error('Omi boolean is malformed');
  return value;
}
function date(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string')
    throw new Error('Omi timestamp is malformed');
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (!Number.isFinite(parsed))
    throw new Error('Omi timestamp is malformed');
  return new Date(parsed).toISOString();
}
function milliseconds(value: unknown): number | null {
  const parsed = date(value);
  return parsed === null ? null : Date.parse(parsed);
}
function integer(value: unknown): number {
  if (value === undefined || value === null) return 0;
  let parsed: number;
  if (typeof value === 'string') {
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new Error('Omi order is malformed');
    }
    parsed = Number(value);
  } else if (typeof value === 'number' && Number.isSafeInteger(value)) {
    parsed = value;
  } else {
    throw new Error('Omi order is malformed');
  }
  if (!Number.isSafeInteger(parsed)) {
    throw new Error('Omi order is malformed');
  }
  return parsed;
}
function presentBool(value: unknown): void {
  if (value === undefined) return;
  if (typeof value !== 'boolean') throw new Error('Omi boolean is malformed');
}
function presentNullableInt(value: unknown): void {
  if (value === undefined || value === null) return;
  integer(value);
}
function presentDefaultInt(value: unknown): void {
  if (value === undefined) return;
  if (value === null) throw new Error('Omi order is malformed');
  integer(value);
}
function presentNullableString(value: unknown): void {
  if (value === undefined || value === null) return;
  text(value);
}
function presentDefaultString(value: unknown): void {
  if (value === undefined) return;
  text(value);
}
function presentNullableDate(value: unknown): void {
  date(value);
}
function presentDefaultDouble(value: unknown): void {
  if (value === undefined) return;
  if (value === null) throw new Error('Omi order is malformed');
  presentNullableDouble(value);
}
function presentNullableDouble(value: unknown): void {
  if (value === undefined || value === null) return;
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new Error('Omi order is malformed');
    }
    const parsed = Number(value);
    if (value === '' || !Number.isFinite(parsed)) {
      throw new Error('Omi order is malformed');
    }
    return;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error('Omi order is malformed');
  }
}
function presentRequiredDouble(value: unknown): void {
  if (value === undefined || value === null) {
    throw new Error('Omi order is malformed');
  }
  presentNullableDouble(value);
}
function presentGeolocation(value: unknown): void {
  if (value === undefined || value === null) return;
  const geolocation = object(value);
  presentRequiredDouble(geolocation.latitude);
  presentRequiredDouble(geolocation.longitude);
  presentNullableDouble(geolocation.accuracy);
  presentNullableDouble(geolocation.altitude);
  presentNullableDate(geolocation.captured_at);
  presentNullableDate(geolocation.time);
  presentNullableString(geolocation.address);
  presentNullableString(geolocation.capture_source);
  presentNullableString(geolocation.google_place_id);
  presentNullableString(geolocation.location_type);
}
function presentRequiredDate(value: unknown): void {
  if (date(value) === null) {
    throw new Error('Omi timestamp is malformed');
  }
}
function presentRequiredDoubleList(value: unknown): void {
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    presentRequiredDouble(item);
  }
}
function presentCalendarEvent(value: unknown): void {
  if (value === undefined || value === null) return;
  const event = object(value);
  text(event.event_id);
  text(event.title);
  presentRequiredDate(event.start_time);
  presentRequiredDate(event.end_time);
  presentNullableString(event.html_link);
  presentUnusedStringListItems(event.attendees);
  presentUnusedStringListItems(event.attendee_emails);
}
function presentAudioFiles(value: unknown): void {
  if (value === undefined) return;
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    const file = object(item);
    text(file.id);
    text(file.uid);
    text(file.conversation_id);
    presentNullableString(file.provider);
    presentRequiredDouble(file.duration);
    presentRequiredDoubleList(file.chunk_timestamps);
    presentNullableDate(file.started_at);
  }
}
function presentConversationAudio(value: unknown): void {
  if (value === undefined || value === null) return;
  const audio = object(value);
  text(audio.audio_files_fingerprint);
  presentNullableString(audio.content_type);
  presentRequiredDouble(audio.duration);
  presentRequiredDouble(audio.captured_duration);
  presentNullableDate(audio.built_at);
  if (audio.spans === undefined) return;
  if (!Array.isArray(audio.spans)) throw new Error('Omi list is malformed');
  for (const item of audio.spans) {
    const span = object(item);
    text(span.file_id);
    presentRequiredDouble(span.artifact_offset);
    presentRequiredDouble(span.len);
    presentRequiredDouble(span.wall_offset);
  }
}
function presentPhotos(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) throw new Error('Omi photos are malformed');
  for (const item of value) {
    const photo = object(item);
    presentNullableDate(photo.created_at);
    presentNullableString(photo.base64);
    presentNullableString(photo.content_type);
    presentNullableString(photo.data_protection_level);
    presentNullableString(photo.description);
    presentNullableString(photo.id);
    presentNullableString(photo.storage_id);
  }
}
function presentActionItems(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    const action = object(item);
    text(action.description);
    presentNullableString(action.candidate_action);
    presentNullableString(action.capture_kind);
    presentNullableString(action.capture_owner);
    presentNullableString(action.context);
    presentNullableString(action.conversation_id);
    presentNullableString(action.due_certainty);
    presentNullableString(action.owner_name);
    presentNullableString(action.target_task_id);
    presentNullableDouble(action.capture_confidence);
    presentNullableDouble(action.ownership_confidence);
    presentNullableDate(action.completed_at);
    presentNullableDate(action.created_at);
    presentNullableDate(action.due_at);
    presentNullableDate(action.updated_at);
    presentUnusedStringListItems(action.source_segment_ids);
  }
}
function presentStructuredSections(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) return;
  for (const item of value) {
    const section = object(item);
    presentNullableString(section.heading);
    presentNullableString(section.body_markdown);
    presentUnusedStringListItems(section.source_segment_ids);
  }
}
function presentAppResults(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) return;
  for (const item of value) {
    const row = object(item);
    presentNullableString(row.content);
  }
}
function presentSuggestedSummarizationApps(value: unknown): void {
  presentUnusedStringListItems(value);
}
function presentUnusedStringListItems(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) return;
  for (const item of value) {
    text(item);
  }
}
function presentTranslations(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) return;
  for (const item of value) {
    const row = object(item);
    presentNullableString(row.lang);
    presentNullableString(row.text);
  }
}
function presentStructuredEvents(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    const event = object(item);
    text(event.title);
    presentNullableString(event.description);
    presentRequiredDate(event.start);
    presentDefaultInt(event.duration);
  }
}
function presentRequiredInt(value: unknown): void {
  if (value === undefined || value === null) {
    throw new Error('Omi order is malformed');
  }
  integer(value);
}
function presentClientProcessing(value: unknown): void {
  if (value === undefined || value === null) return;
  const processing = object(value);
  text(processing.transcript_sha256);
  presentRequiredInt(processing.schema_version);
  const provenance = object(processing.provenance);
  text(provenance.device_class);
  text(provenance.model_id);
  text(provenance.runtime);
  presentRequiredDate(provenance.generated_at);
  const structure = object(processing.structure);
  text(structure.title);
  presentDefaultString(structure.category);
  presentDefaultString(structure.emoji);
  presentDefaultString(structure.overview);
  if (structure.sections !== undefined && structure.sections !== null) {
    if (Array.isArray(structure.sections)) {
      for (const item of structure.sections) {
        const section = object(item);
        text(section.heading);
        text(section.body_markdown);
      }
    }
  }
  if (structure.events !== undefined && structure.events !== null) {
    if (!Array.isArray(structure.events)) throw new Error('Omi list is malformed');
    for (const item of structure.events) {
      const event = object(item);
      text(event.title);
      presentDefaultString(event.description);
      presentRequiredDate(event.start);
      presentRequiredInt(event.duration);
    }
  }
  if (processing.action_items !== undefined && processing.action_items !== null) {
    if (Array.isArray(processing.action_items)) {
      for (const item of processing.action_items) {
        const action = object(item);
        text(action.description);
      }
    }
  }
}
function presentNullableStringList(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    text(item);
  }
}
function presentNullableMap(value: unknown): void {
  if (value === undefined || value === null) return;
  object(value);
}
function presentUnusedMapListItems(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) return;
  for (const item of value) {
    object(item);
  }
}
function presentCaptureContext(value: unknown): void {
  if (value === undefined || value === null) return;
  const context = object(value);
  presentNullableString(context.attribution);
  presentNullableDate(context.captured_at);
  presentNullableString(context.independence_group);
  presentNullableString(context.lineage_id);
  presentUnusedMapListItems(context.quote_refs);
  presentNullableString(context.source_id);
  presentNullableString(context.source_signal);
  text(context.source_type);
  presentNullableString(context.source_version);
}
function presentEvidence(value: unknown): void {
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) throw new Error('Omi list is malformed');
  for (const item of value) {
    const evidence = object(item);
    text(evidence.evidence_id);
    text(evidence.independence_group);
    presentNullableMap(evidence.artifact_ref);
    presentDefaultDouble(evidence.capture_confidence);
    presentNullableDate(evidence.captured_at);
    presentNullableString(evidence.client_device_id);
    presentNullableDate(evidence.created_at);
    presentDefaultString(evidence.extractor_id);
    presentDefaultString(evidence.extractor_version);
    presentDefaultString(evidence.redaction_status);
    presentNullableString(evidence.source_id);
    presentDefaultString(evidence.source_signal);
    presentDefaultString(evidence.source_type);
    presentNullableString(evidence.attribution);
    presentNullableString(evidence.lineage_id);
    presentNullableString(evidence.source_version);
    presentUnusedMapListItems(evidence.quote_refs);
  }
}
function validateGeneratedMemory(row: Record<string, unknown>): void {
  text(row.uid);
  if (milliseconds(row.created_at) === null) {
    throw new Error('Omi timestamp is malformed');
  }
  if (milliseconds(row.updated_at) === null) {
    throw new Error('Omi timestamp is malformed');
  }
  presentNullableString(row.app_id);
  presentNullableMap(row.arguments);
  presentNullableDate(row.as_of);
  presentNullableString(row.belief_class);
  presentNullableDate(row.belief_computed_at);
  presentCaptureContext(row.capture_context);
  presentNullableString(row.canonical_memory_id);
  presentNullableDouble(row.capture_confidence);
  presentNullableStringList(row.capture_device_ids);
  presentDefaultString(row.category);
  presentDefaultInt(row.curation_weight);
  presentNullableDouble(row.currency);
  presentNullableString(row.currency_band);
  presentNullableString(row.data_protection_level);
  presentNullableString(row.durability);
  presentBool(row.edited);
  presentEvidence(row.evidence);
  presentNullableDouble(row.half_life_days);
  presentNullableString(row.headline);
  presentBool(row.intent_backed);
  presentBool(row.is_baseline);
  presentBool(row.is_dismissed);
  presentBool(row.is_locked);
  presentBool(row.is_read);
  presentBool(row.kg_extracted);
  presentNullableString(row.layer);
  presentNullableString(row.ledger_status);
  presentBool(row.manually_added);
  presentNullableString(row.memory_id);
  presentNullableString(row.memory_tier);
  presentNullableStringList(row.object_entity_ids);
  presentNullableString(row.predicate);
  presentNullableMap(row.qualifiers);
  presentBool(row.reviewed);
  presentNullableString(row.scoring);
  presentDefaultString(row.subject_attribution);
  presentNullableString(row.subject_entity_id);
  presentNullableString(row.subject_scope);
  presentNullableStringList(row.tags);
  presentNullableMap(row.trigger_condition);
  presentNullableStringList(row.uncertainty_reasons);
  presentNullableDate(row.valid_at);
  presentNullableDate(row.valid_to);
  presentNullableDouble(row.veracity);
  presentNullableString(row.visibility);
  presentNullableString(row.write_reason);
}
function rows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length > limit)
    throw new Error('Omi list is malformed');
  const seen = new Set<string>();
  return value.map(item => {
    const row = object(item),
      key = id(row.id);
    if (key !== '') {
      if (seen.has(key)) throw new Error('Omi IDs are duplicated');
      seen.add(key);
    }
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
    if (visibleDisplayText(value) !== value) {
      throw new Error('Omi transcript is malformed');
    }
    const parsed = Number(value);
    if (value === '' || !Number.isFinite(parsed)) {
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
  personId?: string;
}[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error('Omi transcript is malformed');
  }
  return value.map(raw => {
    const segment = object(raw);
    presentNullableString(segment.id);
    presentNullableString(segment.stt_provider);
    const personId =
      segment.person_id === undefined || segment.person_id === null
        ? undefined
        : text(segment.person_id);
    presentNullableInt(segment.speaker_id);
    presentTranslations(segment.translations);
    return {
      text: text(segment.text, ''),
      speaker: segment.speaker == null ? 'SPEAKER_00' : text(segment.speaker),
      isUser: bool(segment.is_user),
      start: finiteClock(segment.start),
      end: finiteClock(segment.end),
      ...(personId === undefined ? {} : {personId}),
    };
  });
}
export async function loadOmiConversations(
  read: Read,
  cursor: string | null,
  loadPeopleNames: () => Promise<ReadonlyMap<string, string>> = async () =>
    new Map(),
): Promise<DomainRead<ConversationProjection>> {
  const start = offset(cursor);
  const records = rows(
    await read(`/v1/conversations?limit=${limit}&offset=${start}`),
  );
  const drafts = records.map(row => {
    const structured = object(row.structured);
    const structuredTitle = text(structured.title, ''),
      summary = text(structured.overview, '');
    const discarded = bool(row.discarded);
    const listSegments = discardedTranscriptSegments(row.transcript_segments);
    const discardedSegments = discarded ? listSegments : [];
    const createdAt = date(row.created_at);
    if (createdAt === null)
      throw new Error('Omi conversation creation time is malformed');
    const namedVisibility = text(row.visibility, 'private');
    const visibility = ['private', 'public', 'shared'].includes(namedVisibility)
      ? namedVisibility
      : 'private';
    const status = text(row.status, 'completed');
    const photos = photoCount(row.photos);
    if (!isOptionalCaptureTimestamp(row.captured_at_ms)) {
      throw new Error('Omi captured_at_ms is malformed');
    }
    presentNullableString(row.app_id);
    presentNullableString(row.call_id);
    presentNullableString(row.client_device_id);
    presentNullableString(row.client_platform);
    presentNullableString(row.data_protection_level);
    presentNullableString(row.language);
    presentNullableString(row.meeting_treatment_reason);
    presentNullableString(row.processing_conversation_id);
    presentNullableString(row.processing_memory_id);
    presentNullableString(row.processing_state);
    presentGeolocation(row.geolocation);
    presentNullableDouble(row.meeting_duration_s);
    presentNullableDouble(row.meeting_dedup_speech_s);
    presentCalendarEvent(row.calendar_event);
    presentAudioFiles(row.audio_files);
    presentConversationAudio(row.conversation_audio);
    presentPhotos(row.photos);
    presentActionItems(structured.action_items);
    presentStructuredSections(structured.sections);
    presentStructuredEvents(structured.events);
    presentAppResults(row.apps_results);
    presentAppResults(row.plugins_results);
    presentSuggestedSummarizationApps(row.suggested_summarization_apps);
    presentNullableMap(row.external_data);
    presentClientProcessing(row.client_processing);
    const emoji = conversationStructuredEmojiCopy(
      structured.emoji === undefined || structured.emoji === null
        ? structured.emoji
        : text(structured.emoji),
    );
    const category = conversationStructuredCategoryCopy(
      structured.category === undefined || structured.category === null
        ? structured.category
        : text(structured.category),
    );
    return {
      row,
      structuredTitle,
      summary,
      discarded,
      discardedSegments,
      listSegments,
      createdAt,
      visibility,
      status,
      photos,
      emoji,
      category,
    };
  });
  const needsPeople = drafts.some(({discardedSegments}) =>
    discardedSegments.some(segment => segment.personId !== undefined),
  );
  const peopleNames = needsPeople
    ? await loadPeopleNames().then(
        value => value,
        () => new Map<string, string>(),
      )
    : new Map<string, string>();
  const items = drafts.map(
    ({
      row,
      structuredTitle,
      summary,
      discarded,
      discardedSegments,
      listSegments,
      createdAt,
      visibility,
      status,
      photos,
      emoji,
      category,
    }) => {
      const transcriptEndSeconds =
        conversationTranscriptEndSeconds(listSegments);
      const title = discarded
        ? conversationDiscardedTranscriptCopy(discardedSegments, peopleNames)
        : structuredTitle;
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
        ...(emoji === undefined ? {} : {emoji}),
        ...(category === undefined ? {} : {category}),
        ...(photos === 0 ? {} : {photoCount: photos}),
        ...(row.captured_at_ms === undefined
          ? {}
          : {capturedAtMs: row.captured_at_ms}),
        ...(transcriptEndSeconds === null ? {} : {transcriptEndSeconds}),
      };
    },
  );
  return {apiContract: 'omi', items, page: page(start, items.length)};
}
function memoryItem(row: Record<string, unknown>): MemoryProjection {
  validateGeneratedMemory(row);
  const content = text(row.content),
    created = milliseconds(row.created_at);
  const parsedConversationId =
    row.conversation_id == null ? null : text(row.conversation_id);
  const conversation =
    parsedConversationId === null ||
    visibleDisplayText(parsedConversationId) === ''
      ? null
      : parsedConversationId;
  const ledgerSlot = text(row.slot, '');
  const ledgerKind = text(row.kind, '');
  const ledgerSchema = text(row.ledger_schema_version, '');
  const ledgerBody = visibleDisplayText(text(row.body, ''));
  const playbook =
    ledgerSchema === 'knowledge_ledger.v1' && ledgerKind === 'document'
      ? ledgerBody
      : '';
  const captureDeviceLabel = memoryCaptureDeviceCopy(
    text(row.primary_capture_device, ''),
  );
  const knowledgeKind =
    ledgerKind === 'fact' ||
    ledgerKind === 'document' ||
    ledgerKind === 'trigger';
  const knowledgeLedger =
    ledgerSchema === 'knowledge_ledger.v1' && knowledgeKind;
  const supersededBy = visibleDisplayText(
    row.superseded_by == null ? '' : text(row.superseded_by),
  );
  const intentBacked = bool(row.intent_backed);
  const deleted = bool(row.deleted);
  const invalidAt = date(row.invalid_at);
  const userReview = optionalBool(row.user_review);
  const currentLedger =
    knowledgeLedger &&
    intentBacked &&
    !deleted &&
    invalidAt == null &&
    supersededBy === '' &&
    userReview !== false;
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
    ...(visibleDisplayText(ledgerSlot) === '' ? {} : {ledgerSlot}),
    ...(playbook === '' ? {} : {ledgerBody: playbook}),
    ...(bool(row.is_baseline) ? {isBaseline: true} : {}),
    ...(captureDeviceLabel === null ? {} : {captureDeviceLabel}),
    ...(bool(row.is_locked) ? {locked: true} : {}),
    ...(knowledgeLedger && !currentLedger ? {history: true} : {}),
  };
}
export async function loadOmiMemories(
  read: Read,
  cursor: string | null,
): Promise<DomainRead<MemoryProjection>> {
  const start = offset(cursor);
  const records = rows(
    await read(`/v3/memories?limit=${limit}&offset=${start}`),
  );
  const items = records.map(memoryItem);
  let ledgerHistoryTruncated = false;
  if (start === 0) {
    const seen = new Set(items.map(item => item.id));
    const historyLimit = 500;
    const maxHistoryPages = 10;
    let historyOffset = 0;
    for (let pageIndex = 0; pageIndex < maxHistoryPages; pageIndex++) {
      let raw: unknown;
      try {
        raw = await read(
          `/v3/memories/ledger-history?limit=${historyLimit}&offset=${historyOffset}`,
        );
      } catch {
        break;
      }
      if (!Array.isArray(raw)) break;
      const history = raw.slice(0, historyLimit);
      let projected: MemoryProjection[];
      try {
        projected = history.map(item => memoryItem(object(item)));
      } catch {
        break;
      }
      for (const item of projected) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);
        items.push(item);
      }
      if (history.length < historyLimit) break;
      historyOffset += history.length;
      if (pageIndex === maxHistoryPages - 1) ledgerHistoryTruncated = true;
    }
  }
  return {
    apiContract: 'omi',
    items,
    page: page(start, records.length),
    ...(ledgerHistoryTruncated ? {ledgerHistoryTruncated: true} : {}),
  };
}
export async function loadOmiTasks(
  read: Read,
  cursor: string | null,
): Promise<TaskRead> {
  const start = offset(cursor);
  const envelope = object(
    await read(`/v1/action-items?limit=${limit}&offset=${start}`),
  );
  const hasMore = bool(envelope.has_more);
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
    presentNullableDouble(row.due_confidence);
    presentNullableDate(row.export_date);
    presentNullableString(row.apple_reminder_id);
    presentNullableString(row.conversation_id);
    presentNullableString(row.goal_id);
    presentNullableString(row.priority);
    presentNullableString(row.recurrence_parent_id);
    presentNullableString(row.recurrence_rule);
    presentDefaultString(row.status);
    presentNullableString(row.superseded_by);
    presentNullableString(row.workstream_id);
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
        text(ref.id);
        presentNullableString(ref.device_id);
        presentNullableString(ref.excerpt_hash);
        presentNullableString(ref.version);
        presentNullableString(ref.kind);
        presentNullableString(ref.scope);
        presentNullableDouble(ref.start_seconds);
        presentNullableDouble(ref.end_seconds);
        presentUnusedStringListItems(ref.transcript_segment_ids);
        return JSON.stringify(ref);
      }),
      sortOrder: integer(row.sort_order),
      indentLevel: integer(row.indent_level),
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
      hasMore,
      bool(envelope.truncated),
      true,
    ),
    accountEpoch: null,
    apiContract: 'omi',
  };
}
