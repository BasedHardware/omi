import {
  loadOmiDevApiKeys,
  loadOmiMcpApiKeys,
  parseOmiDeveloperKeys,
} from './legacyOmiDeveloperKeys';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET developer keys and omits empty names and full secrets', () => {
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
        {id: 'key-empty', name: ' \t', key_prefix: 'omi_sk_cd'},
        {
          id: 'key-undated',
          name: 'Legacy',
          key_prefix: 'omi_sk_ef',
          created_at: 'not-a-date',
          scopes: [],
        },
      ]),
    ),
  ).toEqual([
    {
      id: 'key-1',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-09-09T12:00:00.000Z'),
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
    {id: 'key-undated', name: 'Legacy', keyPrefix: 'omi_sk_ef'},
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
      {id: 'kept', name: 'Local', key_prefix: 'omi_sk_ab'},
      {
        id: 'many-scopes',
        name: 'Wide',
        key_prefix: 'omi_sk_cd',
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
      {id: 'kept', name: 'Local', key_prefix: 'omi_sk_ab'},
      {
        id: 'long-scope',
        name: 'Wide',
        key_prefix: 'omi_sk_cd',
        scopes: [scope],
      },
    ]),
  );
  expect(keys.map(row => row.id)).toEqual(['kept', 'long-scope']);
  expect(keys.find(row => row.id === 'long-scope')?.scopes).toEqual([scope]);
});

test('keeps GET developer keys when created_at exceeds 100', () => {
  const createdAt = `2026-04-01T12:00:00.${'0'.repeat(80)}Z`;
  expect(createdAt.length).toBe(101);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-long',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: createdAt,
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-long',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-04-01T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-null', name: 'Local', key_prefix: 'omi_sk_ab', created_at: null},
        {id: 'key-kept', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {id: 'key-null', name: 'Local', keyPrefix: 'omi_sk_ab'},
    {id: 'key-kept', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
});

test('keeps GET developer keys when created_at exceeds 10000', () => {
  const createdAt = `2026-04-01T12:00:00.${'0'.repeat(9980)}Z`;
  expect(createdAt.length).toBe(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {
          id: 'key-long',
          name: 'Local',
          key_prefix: 'omi_sk_ab',
          created_at: createdAt,
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-long',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-04-01T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
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
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {
      id: 'key-hour',
      name: 'Local',
      keyPrefix: 'omi_sk_ab',
      createdAtMs: Date.parse('2026-09-09T12:00:00.000Z'),
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
});

test('keeps GET developer keys when id or key_prefix exceeds 256', () => {
  const id = 'k'.repeat(257);
  const keyPrefix = 'p'.repeat(257);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id, name: 'Local', key_prefix: 'omi_sk_ab'},
        {id: 'key-prefix', name: 'Wide', key_prefix: keyPrefix},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {id, name: 'Local', keyPrefix: 'omi_sk_ab'},
    {id: 'key-prefix', name: 'Wide', keyPrefix: keyPrefix},
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
});

test('keeps GET developer keys when key_prefix or a scope exceeds 10000', () => {
  const keyPrefix = 'p'.repeat(10001);
  const scope = 's'.repeat(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-prefix', name: 'Wide', key_prefix: keyPrefix},
        {
          id: 'key-scope',
          name: 'Scoped',
          key_prefix: 'omi_sk_cd',
          scopes: [scope],
        },
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_ef'},
      ]),
    ),
  ).toEqual([
    {id: 'key-prefix', name: 'Wide', keyPrefix: keyPrefix},
    {
      id: 'key-scope',
      name: 'Scoped',
      keyPrefix: 'omi_sk_cd',
      scopes: [scope],
    },
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_ef'},
  ]);
});

test('does not omit neighboring GET developer keys when the catalogue exceeds 1000', () => {
  const rows = Array.from({length: 1001}, (_, index) => ({
    id: `key-${index}`,
    name: `Key ${index}`,
    key_prefix: `omi_sk_${index}`,
  }));
  const keys = parseOmiDeveloperKeys(JSON.stringify(rows));
  expect(keys[0]).toEqual({
    id: 'key-0',
    name: 'Key 0',
    keyPrefix: 'omi_sk_0',
  });
  expect(keys[1000]).toEqual({
    id: 'key-1000',
    name: 'Key 1000',
    keyPrefix: 'omi_sk_1000',
  });
  expect(keys).toHaveLength(1001);
});

test('keeps GET developer keys when a name exceeds 10000', () => {
  const name = 'L'.repeat(10001);
  expect(
    parseOmiDeveloperKeys(
      JSON.stringify([
        {id: 'key-long', name, key_prefix: 'omi_sk_ab'},
        {id: 'key-neighbor', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
      ]),
    ),
  ).toEqual([
    {id: 'key-long', name, keyPrefix: 'omi_sk_ab'},
    {id: 'key-neighbor', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
});

test('loadOmiDevApiKeys and loadOmiMcpApiKeys name resolved GET keys and omit failures', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/dev/keys') {
      return {
        id: 'dev',
        status: 200,
        body: JSON.stringify([
          {id: 'dev-1', name: 'Local', key_prefix: 'omi_sk_ab'},
        ]),
      };
    }
    if (input.path === '/v1/mcp/keys') {
      return {
        id: 'mcp',
        status: 200,
        body: JSON.stringify([
          {id: 'mcp-1', name: 'Cursor', key_prefix: 'omi_mcp_cd'},
        ]),
      };
    }
    return {id: 'keys', status: 404, body: '[]'};
  });
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDevApiKeys(backend)).toEqual([
    {id: 'dev-1', name: 'Local', keyPrefix: 'omi_sk_ab'},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/dev/keys',
  });
  expect(await loadOmiMcpApiKeys(backend)).toEqual([
    {id: 'mcp-1', name: 'Cursor', keyPrefix: 'omi_mcp_cd'},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/mcp/keys',
  });
  request.mockResolvedValueOnce({id: 'dev', status: 404, body: '[]'});
  expect(await loadOmiDevApiKeys(backend)).toEqual([]);
  request.mockResolvedValueOnce({id: 'mcp', status: 200, body: '{'});
  expect(await loadOmiMcpApiKeys(backend)).toEqual([]);
});
