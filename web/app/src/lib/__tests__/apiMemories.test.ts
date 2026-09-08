import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { createMemory, getMemories } from '@/lib/api';

describe('getMemories ledger boundary', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it('normalizes malformed/future rows at the used API consumer without dropping text rows', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify([
            {
              id: 'legacy',
              uid: 'web-user-1',
              content: 'Legacy text',
              created_at: '2026-08-23T00:00:00Z',
              updated_at: '2026-08-23T00:00:00Z',
              layer: 'long_term',
            },
            {
              id: 'future',
              uid: 'web-user-1',
              content: 'Future text',
              created_at: '2026-08-23T00:00:00Z',
              updated_at: '2026-08-23T00:00:00Z',
              layer: 'long_term',
              ledger_schema_version: 'knowledge_ledger.v2',
              kind: 'fact',
              slot: 'future-slot',
              body: 'future-body',
              trigger_condition: { unsupported: true },
              intent_backed: true,
              curation_weight: 3,
              write_reason: 'direct_user_statement',
              subject_entity_id: 'user-1',
              evidence: [
                null,
                { evidence_id: 'future-evidence' },
                {
                  evidence_id: 'future-evidence',
                  independence_group: 'future-group',
                  extra: true,
                },
              ],
            },
            { id: 'bad', uid: 'web-user-1', content: '   ' },
          ]),
          { headers: { 'content-type': 'application/json' } },
        ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const memories = await getMemories();

    expect(memories).toHaveLength(2);
    expect(memories.map((memory) => memory.content)).toEqual([
      'Legacy text',
      'Future text',
    ]);
    expect(memories[0]).not.toHaveProperty('kind');
    expect(memories[1]).not.toHaveProperty('kind');
    expect(memories[1].evidence).toEqual([
      { evidence_id: 'future-evidence', independence_group: 'future-group', extra: true },
    ]);
    for (const field of [
      'kind',
      'slot',
      'body',
      'trigger_condition',
      'intent_backed',
      'curation_weight',
      'write_reason',
      'subject_entity_id',
    ]) {
      expect(memories[1]).not.toHaveProperty(field);
    }
  });

  it('normalizes the actual createMemory response before returning it', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            id: 'created',
            uid: 'web-user-1',
            content: 'Created text',
            created_at: '2026-08-23T00:00:00Z',
            updated_at: '2026-08-23T00:00:00Z',
            ledger_schema_version: 'knowledge_ledger.v1',
            kind: 'fact',
            slot: 'preferred_name',
            body: 'wrong kind',
            trigger_condition: { wrong: true },
            curation_weight: '3',
            intent_backed: 'true',
            evidence: [
              { evidence_id: 'created-evidence', independence_group: 'created-group' },
            ],
          }),
          { headers: { 'content-type': 'application/json' } },
        ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const memory = await createMemory({ content: 'Created text' });

    expect(memory).toMatchObject({
      id: 'created',
      content: 'Created text',
      kind: 'fact',
      slot: 'preferred_name',
      evidence: [
        { evidence_id: 'created-evidence', independence_group: 'created-group' },
      ],
    });
    expect(memory).not.toHaveProperty('body');
    expect(memory).not.toHaveProperty('trigger_condition');
    expect(memory).not.toHaveProperty('curation_weight');
    expect(memory).not.toHaveProperty('intent_backed');
  });
});
