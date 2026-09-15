import {
  loadOmiDevApiKeys,
  loadOmiMcpApiKeys,
  parseOmiDeveloperKeys,
} from './legacyOmiDeveloperKeys';
import type {OmiBackend} from './omiNativeTypes';

const createdAt = '2026-09-09T12:00:00.000Z';
const createdMs = Date.parse(createdAt);

test('names Flutter DevApiKeyListItem empty GET names instead of omitting the key', () => {
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-1',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: '2026-09-09T12:00:00.000Z',
        },
        {
          id: 'key-empty',
          name: ' \t',
          key_prefix: 'omi_sk_cd',
          created_at: createdAt,
        },
        {
          id: 'key-blank',
          name: '',
          key_prefix: 'omi_sk_ef',
          created_at: createdAt,
        },
      ]),
    ),
  ).toEqual([
    {
      id: 'key-1',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-09-09T12:00:00.000Z'),
    },
    {id: 'key-empty', name: '', keyPrefix: 'omi_sk_cd', createdAtMs: createdMs},
    {id: 'key-blank', name: '', keyPrefix: 'omi_sk_ef', createdAtMs: createdMs},
  ]);
});

test('parses GET developer keys and omits full secrets', () => {
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-1',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          key: 'omi_sk_abcdef_secret',
          created_at: '2026-09-09T12:00:00.000Z',
          scopes: [
            'conversations:read',
            'conversations:write',
            'memories:read',
            'memories:write',
            'action_items:read',
            'action_items:write',
            'goals:read',
            'goals:write',
          ],
        },
        {
          id: 'key-empty',
          name: ' \t',
          key_prefix: 'omi_sk_cd',
          created_at: createdAt,
        },
      ]),
    ),
  ).toEqual([
    {
      id: 'key-1',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: createdMs,
      scopes: [
        'conversations:read',
        'conversations:write',
        'memories:read',
        'memories:write',
        'action_items:read',
        'action_items:write',
        'goals:read',
        'goals:write',
      ],
    },
    {id: 'key-empty', name: '', keyPrefix: 'omi_sk_cd', createdAtMs: createdMs},
  ]);
});

test('names Flutter DevApiKeyListItem empty GET scopes instead of inventing Read Only', () => {
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-empty-scope',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: '2026-09-09T12:00:00.000Z',
          scopes: [' \t', ''],
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-empty-scope',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-09-09T12:00:00.000Z'),
      scopes: ['', ''],
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('fails closed for malformed GET developer keys', () => {
  expect(() => parseOmiDeveloperKeys(JSON.stringify({}))).toThrow();
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([{id: 'key-1', name: 'Local', key_prefix: 1}]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-1', name: 'One', key_prefix: 'omi_sk_a'},
        {id: 'key-1', name: 'Dup', key_prefix: 'omi_sk_b'},
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-1', name: 'Local', key_prefix: 'omi_sk_a', scopes: 'read'},
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-1', name: 'Local', key_prefix: 'omi_sk_a', scopes: [1]},
      ]),
    ),
  ).toThrow();
});

test('does not omit neighboring GET developer keys when scopes exceed 32', () => {
  const scopes = Array.from({length: 33}, (_, index) => `scope-${index}`);
  const keys = parseOmiDeveloperKeys(
    JSON.stringify([
      {id: 'kept', name: 'Local', key_prefix: 'omi_sk_ab', created_at: createdAt},
      {
        id: 'many-scopes',
        name: 'Wide',
        key_prefix: 'omi_sk_cd',
        created_at: createdAt,
        scopes,
      },
    ]),
  );
  expect(keys.map(row => row.id)).toEqual(['kept', 'many-scopes']);
  expect(keys.find(row => row.id === 'many-scopes')?.scopes).toEqual(scopes);
});

test('does not omit neighboring GET developer keys when a scope exceeds 256', () => {
  const scope = 's'.repeat(257);
  const keys = parseOmiDeveloperKeys(
    JSON.stringify([
      {id: 'kept', name: 'Local', key_prefix: 'omi_sk_ab', created_at: createdAt},
      {
        id: 'long-scope',
        name: 'Wide',
        key_prefix: 'omi_sk_cd',
        created_at: createdAt,
        scopes: [scope],
      },
    ]),
  );
  expect(keys.map(row => row.id)).toEqual(['kept', 'long-scope']);
  expect(keys.find(row => row.id === 'long-scope')?.scopes).toEqual([scope]);
});

test('keeps GET developer keys when created_at exceeds 100', () => {
  const longCreatedAt = `2026-04-01T12:00:00.${'0'.repeat(80)}Z`;
  expect(longCreatedAt.length).toBe(101);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-long',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: longCreatedAt,
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-long',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-04-01T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('names Flutter DevApiKey fromJson invalid created_at instead of undated success', () => {
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-null', name: 'Local', key_prefix: 'omi_sk_ab', created_at: null},
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow('Omi developer keys are malformed');
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-omitted', name: 'Local', key_prefix: 'omi_sk_ab'},
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow('Omi developer keys are malformed');
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-undated',
          name: 'Legacy',
          key_prefix: 'omi_sk_ef',
          created_at: 'not-a-date',
        },
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow('Omi developer keys are malformed');
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-empty', name: 'Local', key_prefix: 'omi_sk_ab', created_at: ''},
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow('Omi developer keys are malformed');
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-space', name: 'Local', key_prefix: 'omi_sk_ab', created_at: ' \t'},
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow('Omi developer keys are malformed');
});

test('keeps GET developer keys when created_at exceeds 10000', () => {
  const longCreatedAt = `2026-04-01T12:00:00.${'0'.repeat(9980)}Z`;
  expect(longCreatedAt.length).toBe(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-long',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: longCreatedAt,
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-long',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-04-01T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('keeps GET developer keys when created_at uses hour-only offsets Dart DateTime.tryParse accepts', () => {
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-hour',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: '2026-09-09T12:00:00+00',
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-hour',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-09-09T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('keeps GET developer keys when id or key_prefix exceeds 256', () => {
  const id = 'k'.repeat(257);
  const keyPrefix = 'p'.repeat(257);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id, name: 'Local', key_prefix: 'omi_sk_ab', created_at: createdAt},
        {id: 'key-prefix', name: 'Wide', key_prefix: keyPrefix, created_at: createdAt},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {id, name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs: createdMs},
    {id: 'key-prefix', name: 'Wide', keyPrefix: keyPrefix, createdAtMs: createdMs},
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('keeps GET developer keys when an id exceeds 10000', () => {
  const id = 'k'.repeat(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id, name: 'Local', key_prefix: 'omi_sk_ab', created_at: createdAt},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {id, name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs: createdMs},
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('fails closed when a developer key id exceeds 1000000', () => {
  expect(() =>
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'k'.repeat(1_000_001), name: 'Local', key_prefix: 'omi_sk_ab'},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toThrow();
});

test('keeps GET developer keys when key_prefix or a scope exceeds 10000', () => {
  const keyPrefix = 'p'.repeat(10001);
  const scope = 's'.repeat(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-prefix', name: 'Wide', key_prefix: keyPrefix, created_at: createdAt},
        {
          id: 'key-scope',
          name: 'Scoped',
          key_prefix: 'omi_sk_cd',
          created_at: createdAt,
          scopes: [scope],
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_ef', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {id: 'key-prefix', name: 'Wide', keyPrefix: keyPrefix, createdAtMs: createdMs},
    {
      id: 'key-scope',
      name: 'Scoped',
      keyPrefix: 'omi_sk_cd',
      createdAtMs: createdMs,
      scopes: [scope],
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_ef', createdAtMs: createdMs},
  ]);
});

test('does not omit neighboring GET developer keys when the catalogue exceeds 1000', () => {
  const rows = Array.from({length: 1001}, (_, index) => ({
    id: `key-${index}`,
    name: `Key ${index}`,
    key_prefix: `omi_sk_${index}`,
    created_at: createdAt,
  }));
  const keys = parseOmiDeveloperKeys(JSON.stringify(rows));
  expect(keys[0]).toEqual({
    id: 'key-0',
    name: 'Key 0',
    keyPrefix: 'omi_sk_0',
    createdAtMs: createdMs,
  });
  expect(keys[1000]).toEqual({
    id: 'key-1000',
    name: 'Key 1000',
    keyPrefix: 'omi_sk_1000',
    createdAtMs: createdMs,
  });
  expect(keys).toHaveLength(1001);
});

test('keeps GET developer keys when a name exceeds 10000', () => {
  const name = 'L'.repeat(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-long', name, key_prefix: 'omi_sk_ab', created_at: createdAt},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
      ]),
    ),
  ).toEqual([
    {id: 'key-long', name, keyPrefix: 'omi_sk_ab', createdAtMs: createdMs},
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
});

test('loadOmiDevApiKeys and loadOmiMcpApiKeys name resolved GET keys', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/dev/keys') {
      return {
        id: 'dev',
        status: 200,
        body: JSON.stringify([
          {id: 'dev-1', name: 'Local', key_prefix: 'omi_sk_ab', created_at: createdAt},
        ]),
      };
    }
    if (input.path === '/v1/mcp/keys') {
      return {
        id: 'mcp',
        status: 200,
        body: JSON.stringify([
          {id: 'mcp-1', name: 'Cursor', key_prefix: 'omi_mcp_cd', created_at: createdAt},
        ]),
      };
    }
    return {id: 'keys', status: 404, body: '[]'};
  });
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDevApiKeys(backend)).toEqual([
    {id: 'dev-1', name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs: createdMs},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/dev/keys',
  });
  expect(await loadOmiMcpApiKeys(backend)).toEqual([
    {id: 'mcp-1', name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs: createdMs},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/mcp/keys',
  });
});

test('loadOmiDevApiKeys and loadOmiMcpApiKeys name HTTP 404 instead of empty success', async () => {
  const request = jest.fn(async () => ({
    id: 'keys',
    status: 404,
    body: '[]',
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiDevApiKeys(backend)).rejects.toThrow(
    'Omi developer keys are malformed',
  );
  await expect(loadOmiMcpApiKeys(backend)).rejects.toThrow(
    'Omi developer keys are malformed',
  );
});

test('loadOmiDevApiKeys and loadOmiMcpApiKeys keep honest GET empty keys', async () => {
  const request = jest.fn(async () => ({
    id: 'keys',
    status: 200,
    body: '[]',
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDevApiKeys(backend)).toEqual([]);
  expect(await loadOmiMcpApiKeys(backend)).toEqual([]);
});

test('loadOmiDevApiKeys names HTTP 500 instead of empty success', async () => {
  const request = jest.fn(async () => ({
    id: 'dev',
    status: 500,
    body: '{"error":"internal"}',
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiDevApiKeys(backend)).rejects.toThrow(
    'Omi developer keys are malformed',
  );
});

test('loadOmiMcpApiKeys names malformed GET instead of empty success', async () => {
  const request = jest.fn(async () => ({
    id: 'mcp',
    status: 200,
    body: '{',
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiMcpApiKeys(backend)).rejects.toThrow();
});
