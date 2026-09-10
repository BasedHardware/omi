import {loadOmiFolderName, parseOmiFolderNames} from './legacyOmiFolders';
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

test('fails closed for malformed GET folders', () => {
  expect(() =>
    parseOmiFolderNames(JSON.stringify({id: 'folder-work'})),
  ).toThrow();
  expect(() =>
    parseOmiFolderNames(JSON.stringify([{id: 'folder-work', name: 1}])),
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
