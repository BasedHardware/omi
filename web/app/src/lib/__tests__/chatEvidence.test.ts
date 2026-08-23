import { describe, expect, it } from 'vitest';
import {
  CHAT_EVIDENCE_MAX_REFERENCES,
  CHAT_EVIDENCE_MAX_SUMMARY_CHARS,
  CHAT_EVIDENCE_MAX_TITLE_CHARS,
  parseChatEvidenceEnvelope,
  parseChatEvidenceFromRecord,
} from '@/lib/chatEvidence';

describe('chat evidence parser', () => {
  it('keeps the first reference for a duplicate id', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: [
        {
          id: 'same-id',
          kind: 'conversation_summary',
          state: 'available',
          conversation_id: 'conversation-1',
        },
        {
          id: 'same-id',
          kind: 'conversation_summary',
          state: 'failed',
          conversation_id: 'conversation-2',
        },
      ],
    });

    expect(envelope?.references).toHaveLength(1);
    expect(envelope?.references[0]).toMatchObject({
      id: 'same-id',
      state: 'available',
      conversationId: 'conversation-1',
    });
  });

  it('admits bounded conversation references and preserves all supported states', () => {
    const title = 't'.repeat(CHAT_EVIDENCE_MAX_TITLE_CHARS + 20);
    const summary = 's'.repeat(CHAT_EVIDENCE_MAX_SUMMARY_CHARS + 20);
    const envelope = parseChatEvidenceEnvelope({
      schema_version: 1,
      request_id: 'request-1',
      references: [
        {
          id: 'summary-1',
          kind: 'conversation_summary',
          state: 'available',
          title,
          summary,
          conversation_id: 'conversation-1',
        },
        {
          id: 'segment-1',
          kind: 'conversation_segment',
          state: 'loading',
          conversation_id: 'conversation-1',
          segment_id: 'segment-1',
        },
        ...(['offline', 'pruned', 'failed'] as const).map((state, index) => ({
          id: `state-${index}`,
          kind: 'conversation_summary',
          state,
          conversation_id: 'conversation-1',
        })),
      ],
    });

    expect(envelope).toMatchObject({ schemaVersion: 1, requestId: 'request-1' });
    expect(envelope?.references).toHaveLength(5);
    expect(envelope?.references[0]).toMatchObject({
      title: title.slice(0, CHAT_EVIDENCE_MAX_TITLE_CHARS),
      summary: summary.slice(0, CHAT_EVIDENCE_MAX_SUMMARY_CHARS),
      conversationId: 'conversation-1',
    });
    expect(envelope?.references.map(({ state }) => state)).toEqual([
      'available',
      'loading',
      'offline',
      'pruned',
      'failed',
    ]);
  });

  it('drops malformed and unsupported references before they reach the UI', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: [
        { id: 'screen', kind: 'screen', state: 'available', frame_id: 'frame-1' },
        { id: 'keyframe', kind: 'keyframe', state: 'available', frame_id: 'frame-1' },
        { id: 'request', kind: 'request', state: 'available', request_id: 'request-1' },
        {
          id: 'unknown',
          kind: 'future_kind',
          state: 'available',
          conversation_id: 'conversation-1',
        },
        { id: 'missing-target', kind: 'conversation_summary', state: 'available' },
        null,
        'malformed',
      ],
    });

    expect(envelope?.references).toEqual([]);
  });

  it('fails closed for future or malformed schema versions', () => {
    expect(
      parseChatEvidenceEnvelope({
        schema_version: 99,
        references: [
          {
            id: 'summary',
            kind: 'conversation_summary',
            state: 'available',
            conversation_id: 'conversation-1',
          },
        ],
      }),
    ).toMatchObject({ schemaVersion: 99, references: [] });

    expect(
      parseChatEvidenceEnvelope({
        schema_version: 'not-a-version',
        references: [
          {
            id: 'summary',
            kind: 'conversation_summary',
            state: 'available',
            conversation_id: 'conversation-1',
          },
        ],
      }),
    ).toMatchObject({ schemaVersion: 0, references: [] });
  });

  it('caps the admitted reference list and does not throw on malformed records', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: Array.from(
        { length: CHAT_EVIDENCE_MAX_REFERENCES + 5 },
        (_, index) => ({
          id: `summary-${index}`,
          kind: 'conversation_summary',
          state: 'available',
          conversation_id: 'conversation-1',
        }),
      ),
    });

    expect(envelope?.references).toHaveLength(CHAT_EVIDENCE_MAX_REFERENCES);
    expect(() => parseChatEvidenceFromRecord({ evidence: new Map() })).not.toThrow();
    expect(parseChatEvidenceFromRecord({ evidence: new Map() })).toBeNull();
  });

  it('reads the legacy serialized metadata location without depending on it for text', () => {
    const parsed = parseChatEvidenceFromRecord({
      text: 'authoritative answer',
      metadata: JSON.stringify({
        evidence_refs: [
          {
            id: 'segment-1',
            kind: 'conversation_segment',
            state: 'failed',
            conversation_id: 'conversation-1',
            segment_id: 'segment-1',
            error_message: 'The segment could not be loaded',
          },
        ],
      }),
    });

    expect(parsed?.references[0]).toMatchObject({
      state: 'failed',
      segmentId: 'segment-1',
    });
  });
});
