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
