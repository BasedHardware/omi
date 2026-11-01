import { describe, expect, it } from 'vitest'
import {
  CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS,
  CHAT_EVIDENCE_MAX_REFERENCES,
  CHAT_EVIDENCE_MAX_SUMMARY_CHARS,
  CHAT_EVIDENCE_MAX_TITLE_CHARS,
  chatEvidenceReferenceCanOpen,
  parseChatEvidenceEnvelope,
  parseChatEvidenceFromRecord,
  parseChatEvidenceReference,
  parseKnowledgeLedgerKind,
  parseKnowledgeLedgerMemory,
  parseKnowledgeLedgerStatus,
  parseKnowledgeLedgerSubjectScope
} from './knowledgeLedger'

const baseMemory = {
  id: 'memory-1',
  uid: 'user-1',
  content: 'authoritative text',
  created_at: '2026-08-23T00:00:00Z',
  updated_at: '2026-08-23T00:00:00Z',
  ledger_schema_version: 'knowledge_ledger.v1'
}

describe('knowledge_ledger.v1 memory adapter', () => {
  it('uses authoritative content and does not invent a kind or lifecycle state', () => {
    const parsed = parseKnowledgeLedgerMemory({
      ...baseMemory,
      content: '  The text is authoritative.  ',
      headline: 'Do not substitute this headline',
      kind: 'future_kind',
      status: 'future_status',
      subject_scope: 'future_scope',
      unknown_field: 'ignored'
    })

    expect(parsed).not.toBeNull()
    expect(parsed?.content).toBe('  The text is authoritative.  ')
    expect(parsed?.headline).toBe('Do not substitute this headline')
    expect(parsed?.kind).toBe('unknown')
    expect(parsed?.status).toBe('unknown')
    expect(parsed?.subject_scope).toBe('unknown')
    expect(parsed).not.toHaveProperty('unknown_field')
  })

  it('represents current facts, superseded history, playbook documents, and triggers', () => {
    const fact = parseKnowledgeLedgerMemory({
      ...baseMemory,
      kind: 'fact',
      status: 'active',
      subject_scope: 'primary_user',
      slot: 'home_city',
      intent_backed: true
    })
    const history = parseKnowledgeLedgerMemory({
      ...baseMemory,
      id: 'memory-history',
      kind: 'fact',
      status: 'superseded',
      valid_to: '2026-08-22T00:00:00Z',
      superseded_by: 'memory-1'
    })
    const playbook = parseKnowledgeLedgerMemory({
      ...baseMemory,
      id: 'playbook-1',
      kind: 'document',
      body: 'Bounded playbook body'
    })
    const trigger = parseKnowledgeLedgerMemory({
      ...baseMemory,
      id: 'trigger-1',
      kind: 'trigger',
      trigger_condition: { keywords: ['launch'], app: 'Calendar' }
    })

    expect(fact?.kind).toBe('fact')
    expect(fact?.slot).toBe('home_city')
    expect(history?.status).toBe('superseded')
    expect(history?.superseded_by).toBe('memory-1')
    expect(playbook?.kind).toBe('document')
    expect(playbook?.body).toBe('Bounded playbook body')
    expect(trigger?.kind).toBe('trigger')
    expect(trigger?.trigger_condition).toEqual({ keywords: ['launch'], app: 'Calendar' })
  })

  it('rejects rows without stable identity, text, or required timestamps', () => {
    expect(parseKnowledgeLedgerMemory({ ...baseMemory, id: undefined })).toBeNull()
    expect(parseKnowledgeLedgerMemory({ ...baseMemory, content: '   ' })).toBeNull()
    expect(parseKnowledgeLedgerMemory({ ...baseMemory, updated_at: undefined })).toBeNull()
    expect(parseKnowledgeLedgerMemory(null)).toBeNull()
    expect(parseKnowledgeLedgerKind(' FACT ')).toBe('fact')
    expect(parseKnowledgeLedgerStatus('nope')).toBe('unknown')
    expect(parseKnowledgeLedgerSubjectScope('third_party')).toBe('third_party')
  })

  it('does not infer ledger authority from an ordinary legacy row version', () => {
    const parsed = parseKnowledgeLedgerMemory({
      ...baseMemory,
      ledger_schema_version: undefined,
      version: 1,
      kind: 'fact',
      status: 'active',
      subject_scope: 'primary_user',
      slot: 'legacy-slot',
      intent_backed: true,
      curation_weight: 3,
      write_reason: 'direct_user_statement',
      valid_at: '2026-08-23T00:00:00Z',
      superseded_by: 'other',
      subject_entity_id: 'user-1',
      arguments: { subject: 'user' },
      body: 'must not be treated as a playbook body'
    })

    expect(parsed?.ledger_schema_version).toBeUndefined()
    expect(parsed?.kind).toBeUndefined()
    expect(parsed?.status).toBeUndefined()
    expect(parsed?.subject_scope).toBeUndefined()
    expect(parsed?.body).toBeUndefined()
    for (const field of [
      'slot',
      'intent_backed',
      'curation_weight',
      'write_reason',
      'valid_at',
      'superseded_by',
      'subject_entity_id',
      'arguments'
    ]) {
      expect(parsed).not.toHaveProperty(field)
    }
  })

  it('drops wrong-kind and incorrectly typed v1 authority fields', () => {
    const parsed = parseKnowledgeLedgerMemory({
      ...baseMemory,
      kind: 'fact',
      slot: 'home_city',
      body: 'wrong kind',
      trigger_condition: { wrong: true },
      intent_backed: 'true',
      curation_weight: '3',
      account_generation: '4',
      valid_at: 42,
      object_entity_ids: ['entity-1', 2],
      uncertainty_reasons: ['reason', false],
      evidence: [
        { evidence_id: 'missing-group' },
        { evidence_id: 'valid', independence_group: 'group-1', future_field: true }
      ]
    })

    expect(parsed).toMatchObject({ kind: 'fact', slot: 'home_city' })
    expect(parsed).not.toHaveProperty('body')
    expect(parsed).not.toHaveProperty('trigger_condition')
    expect(parsed).not.toHaveProperty('intent_backed')
    expect(parsed).not.toHaveProperty('curation_weight')
    expect(parsed).not.toHaveProperty('account_generation')
    expect(parsed).not.toHaveProperty('valid_at')
    expect(parsed).not.toHaveProperty('object_entity_ids')
    expect(parsed).not.toHaveProperty('uncertainty_reasons')
    expect(parsed?.evidence).toEqual([
      { evidence_id: 'valid', independence_group: 'group-1', future_field: true }
    ])
  })
})

describe('bounded chat evidence envelope', () => {
  it('parses aliases, caps strings/references, and ignores malformed entries', () => {
    const longId = `  ${'i'.repeat(CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS + 20)}  `
    const longTitle = 't'.repeat(CHAT_EVIDENCE_MAX_TITLE_CHARS + 20)
    const longSummary = 's'.repeat(CHAT_EVIDENCE_MAX_SUMMARY_CHARS + 20)
    const envelope = parseChatEvidenceEnvelope({
      schemaVersion: 1,
      requestId: longId,
      evidence_refs: [
        {
          reference_id: longId,
          type: 'conversation_segment',
          status: 'available',
          title: longTitle,
          preview: longSummary,
          conversationId: 'conversation-1',
          segment_id: 'segment-1',
          metadata: { source: 'fixture' }
        },
        null,
        ...Array.from({ length: CHAT_EVIDENCE_MAX_REFERENCES + 2 }, (_, i) => ({
          id: `ref-${i}`,
          kind: 'request',
          state: 'available',
          request_id: `request-${i}`
        }))
      ]
    })

    expect(envelope?.schemaVersion).toBe(1)
    expect(envelope?.requestId).toHaveLength(CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS)
    expect(envelope?.references).toHaveLength(CHAT_EVIDENCE_MAX_REFERENCES)
    expect(envelope?.references[0]).toMatchObject({
      id: 'i'.repeat(CHAT_EVIDENCE_MAX_IDENTIFIER_CHARS),
      kind: 'conversation_segment',
      state: 'available',
      title: longTitle.slice(0, CHAT_EVIDENCE_MAX_TITLE_CHARS),
      summary: longSummary.slice(0, CHAT_EVIDENCE_MAX_SUMMARY_CHARS),
      conversationId: 'conversation-1',
      segmentId: 'segment-1'
    })
    expect(envelope?.references[0].metadata).toEqual({ source: 'fixture' })
  })

  it('fails closed for an explicitly malformed schema version', () => {
    const envelope = parseChatEvidenceEnvelope({
      schema_version: 'not-a-version',
      references: [{ id: 'ref', kind: 'request', state: 'available', request_id: 'req' }]
    })

    expect(envelope?.schemaVersion).toBe(0)
    expect(envelope?.references[0]).toMatchObject({ kind: 'unknown', state: 'unknown' })
    expect(chatEvidenceReferenceCanOpen(envelope!.references[0])).toBe(false)
  })

  it('bounds error strings and nested metadata without throwing', () => {
    const envelope = parseChatEvidenceEnvelope({
      references: [
        {
          id: 'ref',
          kind: 'request',
          state: 'failed',
          request_id: 'req',
          error_code: 'e'.repeat(500),
          error_message: 'm'.repeat(2_000),
          metadata: {
            nested: { deeply: { tooDeep: { ignored: 'x' } } },
            huge: 'x'.repeat(20_000)
          }
        }
      ]
    })

    expect(envelope?.references[0].errorCode).toHaveLength(128)
    expect(envelope?.references[0].errorMessage).toHaveLength(600)
    expect(JSON.stringify(envelope?.references[0].metadata ?? {}).length).toBeLessThanOrEqual(2_000)
  })

  it('treats malformed direct maps as absent instead of throwing', () => {
    const malformed = { evidence: new Map([[1, 'malformed']]) }
    expect(() => parseChatEvidenceFromRecord(malformed)).not.toThrow()
    expect(parseChatEvidenceFromRecord(malformed)).toBeNull()
  })

  it('maps unknown kinds/states and makes every unavailable ref non-actionable', () => {
    const unknown = parseChatEvidenceReference({
      id: 'unknown',
      kind: 'new_kind',
      state: 'new_state'
    })
    expect(unknown.kind).toBe('unknown')
    expect(unknown.state).toBe('unknown')
    expect(chatEvidenceReferenceCanOpen(unknown)).toBe(false)

    for (const state of ['loading', 'offline', 'pruned', 'failed'] as const) {
      const reference = parseChatEvidenceReference({
        id: 'segment-ref',
        kind: 'conversation_segment',
        state,
        conversation_id: 'conversation-1',
        segment_id: 'segment-1'
      })
      expect(chatEvidenceReferenceCanOpen(reference)).toBe(false)
    }
  })

  it('requires the target identity for an available reference', () => {
    expect(
      chatEvidenceReferenceCanOpen(
        parseChatEvidenceReference({
          id: 'summary',
          kind: 'conversation_summary',
          state: 'available'
        })
      )
    ).toBe(false)
    expect(
      chatEvidenceReferenceCanOpen(
        parseChatEvidenceReference({
          id: 'summary',
          kind: 'conversation_summary',
          state: 'available',
          conversation_id: 'conversation-1'
        })
      )
    ).toBe(true)
    expect(
      chatEvidenceReferenceCanOpen(
        parseChatEvidenceReference({
          id: 'frame',
          kind: 'keyframe',
          state: 'available',
          frame_id: 'frame-1'
        })
      )
    ).toBe(true)
  })

  it('keeps future evidence schemas non-actionable even when v1 fields look valid', () => {
    const future = parseChatEvidenceEnvelope({
      schema_version: 99,
      references: [
        {
          id: 'summary',
          kind: 'conversation_summary',
          state: 'available',
          conversation_id: 'conversation-1'
        }
      ]
    })

    expect(future?.references[0].kind).toBe('unknown')
    expect(future?.references[0].state).toBe('unknown')
    expect(chatEvidenceReferenceCanOpen(future!.references[0])).toBe(false)
  })

  it('decodes direct and serialized metadata envelopes without making text depend on them', () => {
    const direct = parseChatEvidenceFromRecord({
      text: 'authoritative chat answer',
      evidence: { references: [{ id: 'r', kind: 'request', state: 'available', request_id: 'q' }] }
    })
    const metadata = parseChatEvidenceFromRecord({
      text: 'authoritative chat answer',
      metadata: JSON.stringify({ evidence_refs: [{ id: 'r2', kind: 'request', state: 'failed' }] })
    })

    expect(direct?.references[0].requestId).toBe('q')
    expect(metadata?.references[0].state).toBe('failed')
    expect(parseChatEvidenceEnvelope('not an object')).toBeNull()
  })
})
