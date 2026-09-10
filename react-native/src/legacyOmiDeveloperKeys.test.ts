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
        },
        {id: 'key-empty', name: ' \t', key_prefix: 'omi_sk_cd'},
      ]),
    ),
  ).toEqual([{id: 'key-1', name: 'Local', keyPrefix: 'omi_sk_ab'}]);
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
