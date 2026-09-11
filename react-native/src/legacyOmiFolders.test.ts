import {
  loadOmiFolder,
  loadOmiFolderName,
  loadOmiFolderNames,
  parseOmiFolderNames,
  parseOmiFolders,
} from './legacyOmiFolders';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET folder names and omits empty names', () => {
  const names = parseOmiFolderNames(
    JSON.stringify([
      {id: 'folder-work', name: 'Work'},
      {id: 'folder-empty', name: ' \t'},
    ]),
  );
  expect(names.get('folder-work')).toBe('Work');
  expect(names.has('folder-empty')).toBe(false);
});

test('parses GET folder color and omits empty or invalid color', () => {
  expect(
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          color: '#3b82f6',
          icon: '💼',
          conversation_count: 99,
        },
        {id: 'folder-plain', name: 'Plain', color: ' \t'},
        {id: 'folder-bad', name: 'Bad', color: 'blue'},
        {id: 'folder-short', name: 'Short', color: '#fff'},
        {id: 'folder-hashless', name: 'Hashless', color: '00AA11'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-work', name: 'Work', color: '#3B82F6'},
    {id: 'folder-plain', name: 'Plain'},
    {id: 'folder-bad', name: 'Bad'},
    {id: 'folder-short', name: 'Short'},
    {id: 'folder-hashless', name: 'Hashless', color: '#00AA11'},
  ]);
});

test('does not omit a neighboring named folder when stored name cannot project', () => {
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work'},
        {id: 'folder-wart', name: 1},
        {id: 'folder-object', name: {text: 'Nope'}},
      ]),
    ),
  ).toEqual([{id: 'folder-work', name: 'Work'}]);
});

test('fails closed for malformed GET folders', () => {
  expect(() =>
    parseOmiFolderNames(JSON.stringify({id: 'folder-work'})),
  ).toThrow();
  expect(() =>
    parseOmiFolderNames(
      JSON.stringify([
        {id: 'folder-work', name: 'Work'},
        {id: 'folder-work', name: 'Dup'},
      ]),
    ),
  ).toThrow();
});

test('loadOmiFolderNames names resolved GET folders and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {id: 'folder-work', name: 'Work'},
      {id: 'folder-empty', name: ' \t'},
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiFolderNames(backend)).toEqual([
    {id: 'folder-work', name: 'Work'},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/folders',
  });
  expect(request.mock.calls.some(call => call[0].method !== 'GET')).toBe(false);
  request.mockResolvedValueOnce({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {id: 'folder-work', name: 'Work'},
      {id: 'folder-wart', name: 1},
    ]),
  });
  expect(await loadOmiFolderNames(backend)).toEqual([
    {id: 'folder-work', name: 'Work'},
  ]);
  request.mockResolvedValueOnce({id: 'folders', status: 404, body: null});
  expect(await loadOmiFolderNames(backend)).toEqual([]);
  request.mockResolvedValueOnce({id: 'folders', status: 200, body: '{'});
  expect(await loadOmiFolderNames(backend)).toEqual([]);
});

test('loadOmiFolder names a resolved GET folder color and omits misses', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {id: 'folder-work', name: 'Work', color: '#3B82F6', icon: '💼'},
      {id: 'folder-empty', name: ' \t', color: '#EF4444'},
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiFolder(backend, 'folder-work')).toEqual({
    id: 'folder-work',
    name: 'Work',
    color: '#3B82F6',
  });
  expect(await loadOmiFolder(backend, 'folder-empty')).toBeUndefined();
  expect(await loadOmiFolder(backend, 'folder-missing')).toBeUndefined();
  request.mockResolvedValueOnce({id: 'folders', status: 500, body: '[]'});
  expect(await loadOmiFolder(backend, 'folder-work')).toBeUndefined();
});

test('loadOmiFolderName names a resolved GET folder and omits misses', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([{id: 'folder-work', name: 'Work'}]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiFolderName(backend, 'folder-work')).toBe('Work');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/folders',
  });
  expect(await loadOmiFolderName(backend, 'folder-missing')).toBeUndefined();
  request.mockResolvedValueOnce({id: 'folders', status: 500, body: '[]'});
  expect(await loadOmiFolderName(backend, 'folder-work')).toBeUndefined();
});
