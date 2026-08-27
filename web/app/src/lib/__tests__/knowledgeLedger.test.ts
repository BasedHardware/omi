import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseChatEvidenceFromRecord } from '@/lib/chatEvidence';
import { normalizeKnowledgeLedgerMemories } from '@/lib/knowledgeLedger';

const baseMemory = {
  uid: 'web-user-1',
  created_at: '2026-08-23T00:00:00Z',
  updated_at: '2026-08-23T00:00:00Z',
  layer: 'long_term',
};

type JitRuntimeMatrix = {
  memory_rows: Array<Record<string, unknown>>;
  chat_records: Record<'legacy' | 'v1' | 'future', Record<string, unknown>>;
  expected: {
    memory_ids: string[];
    authoritative_ledger_ids: string[];
    readable_text_by_id: Record<string, string>;
    v1_evidence_kind: string;
  };
};

const jitRuntimeMatrix = (): JitRuntimeMatrix => {
  const path = resolve(
    process.cwd(),
    '../../contracts/parity/jit_runtime_contract_matrix.json',
  );
  return JSON.parse(readFileSync(path, 'utf8')) as JitRuntimeMatrix;
};

describe('web knowledge ledger memory boundary', () => {
  it('runs the shared mixed-version JIT contract through the web runtime adapters', () => {
    const matrix = jitRuntimeMatrix();
    const memories = normalizeKnowledgeLedgerMemories(matrix.memory_rows);

    expect(memories.map((memory) => memory.id)).toEqual(matrix.expected.memory_ids);
    expect(
      Object.fromEntries(memories.map((memory) => [memory.id, memory.content])),
    ).toEqual(matrix.expected.readable_text_by_id);
    expect(
      memories
        .filter((memory) => memory.ledger_schema_version === 'knowledge_ledger.v1')
        .map((memory) => memory.id),
    ).toEqual(matrix.expected.authoritative_ledger_ids);

    expect(parseChatEvidenceFromRecord(matrix.chat_records.legacy)).toBeNull();
    const current = parseChatEvidenceFromRecord(matrix.chat_records.v1);
    const future = parseChatEvidenceFromRecord(matrix.chat_records.future);
    expect(current?.references[0]?.kind).toBe(matrix.expected.v1_evidence_kind);
    expect(future?.schemaVersion).toBe(2);
    expect(future?.references).toEqual([]);
    expect(matrix.chat_records.future.text).toBeTruthy();
  });

  it('keeps legacy, v1, and future text rows readable without granting future authority', () => {
    const [legacy, current, future] = normalizeKnowledgeLedgerMemories([
      {
        ...baseMemory,
        id: 'legacy',
        content: 'Legacy text',
        kind: 'fact',
        subject_scope: 'primary_user',
        slot: 'name',
        intent_backed: true,
        curation_weight: 3,
        write_reason: 'direct_user_statement',
        valid_at: '2026-08-23T00:00:00Z',
        superseded_by: 'other',
        arguments: { subject: 'user' },
        subject_entity_id: 'user-1',
      },
      {
        ...baseMemory,
        id: 'current',
        content: 'Current text',
        ledger_schema_version: 'knowledge_ledger.v1',
        kind: ' FACT ',
        subject_scope: ' PRIMARY_USER ',
        slot: 'name',
        body: 42,
        trigger_condition: { should: 'be dropped' },
        intent_backed: 'true',
        curation_weight: '3',
        write_reason: 'not-a-real-reason',
        valid_at: 42,
        arguments: 'not-an-object',
      },
      {
        ...baseMemory,
        id: 'future',
        content: 'Future text',
        ledger_schema_version: 'knowledge_ledger.v2',
        kind: 'fact',
        subject_scope: 'primary_user',
        body: 'Future body must stay inert',
        trigger_condition: { unsupported: true },
        slot: 'future-slot',
        intent_backed: true,
        curation_weight: 3,
        write_reason: 'direct_user_statement',
        valid_at: '2026-08-23T00:00:00Z',
        superseded_by: 'other',
        arguments: { subject: 'user' },
        subject_entity_id: 'user-1',
      },
      { ...baseMemory, id: 'malformed', content: '   ' },
    ]);

    expect(legacy).toMatchObject({ id: 'legacy', content: 'Legacy text' });
    for (const field of [
      'kind',
      'subject_scope',
      'slot',
      'intent_backed',
      'curation_weight',
      'write_reason',
      'valid_at',
      'superseded_by',
      'arguments',
      'subject_entity_id',
    ]) {
      expect(legacy).not.toHaveProperty(field);
    }
    expect(current).toMatchObject({
      id: 'current',
      content: 'Current text',
      kind: 'fact',
      subject_scope: 'primary_user',
      slot: 'name',
    });
    expect(current).not.toHaveProperty('body');
    expect(current).not.toHaveProperty('trigger_condition');
    expect(current).not.toHaveProperty('intent_backed');
    expect(current).not.toHaveProperty('curation_weight');
    expect(current).not.toHaveProperty('write_reason');
    expect(current).not.toHaveProperty('valid_at');
    expect(current).not.toHaveProperty('arguments');
    expect(future).toMatchObject({
      id: 'future',
      content: 'Future text',
      ledger_schema_version: 'knowledge_ledger.v2',
    });
    expect(future).not.toHaveProperty('kind');
    expect(future).not.toHaveProperty('subject_scope');
    expect(future).not.toHaveProperty('body');
    for (const field of [
      'trigger_condition',
      'slot',
      'intent_backed',
      'curation_weight',
      'write_reason',
      'valid_at',
      'superseded_by',
      'arguments',
      'subject_entity_id',
    ]) {
      expect(future).not.toHaveProperty(field);
    }
  });

  it('retains only the field coupled to each v1 kind', () => {
    const [fact, document, trigger] = normalizeKnowledgeLedgerMemories(
      ['fact', 'document', 'trigger'].map((kind) => ({
        ...baseMemory,
        id: kind,
        content: `${kind} text`,
        ledger_schema_version: 'knowledge_ledger.v1',
        kind,
        slot: 'fact-slot',
        body: 'document-body',
        trigger_condition: { app: 'Calendar' },
      })),
    );

    expect(fact).toMatchObject({ slot: 'fact-slot' });
    expect(fact).not.toHaveProperty('body');
    expect(fact).not.toHaveProperty('trigger_condition');
    expect(document).toMatchObject({ body: 'document-body' });
    expect(document).not.toHaveProperty('slot');
    expect(document).not.toHaveProperty('trigger_condition');
    expect(trigger).toMatchObject({ trigger_condition: { app: 'Calendar' } });
    expect(trigger).not.toHaveProperty('slot');
    expect(trigger).not.toHaveProperty('body');
  });

  it('drops malformed evidence entries while retaining authoritative memory text', () => {
    const [memory] = normalizeKnowledgeLedgerMemories([
      {
        ...baseMemory,
        id: 'evidence-memory',
        content: 'Text does not depend on evidence',
        ledger_schema_version: 'knowledge_ledger.v1',
        kind: 'fact',
        evidence: [
          null,
          'malformed',
          { evidence_id: 'missing-group' },
          { independence_group: 'missing-id' },
          { evidence_id: ' ', independence_group: 'group-2' },
          {
            evidence_id: 'valid',
            independence_group: 'group-1',
            future_field: true,
            oversized_future_field: 'x'.repeat(2_000),
          },
        ],
      },
    ]);

    expect(memory).toMatchObject({
      id: 'evidence-memory',
      content: 'Text does not depend on evidence',
    });
    expect(memory.evidence).toEqual([
      {
        evidence_id: 'valid',
        independence_group: 'group-1',
        future_field: true,
        oversized_future_field: 'x'.repeat(1_000),
      },
    ]);
  });
});
