import {
  loadOmiFolder,
  loadOmiFolderName,
  loadOmiFolderNames,
  omiFolderHexColor,
  omiFolderIconCopy,
  parseOmiFolderNames,
  parseOmiFolders,
} from './legacyOmiFolders';
import type {OmiBackend} from './omiNativeTypes';

test('names Flutter FolderTabs empty GET ids instead of omitting them', () => {
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work'},
        {id: ' \t', name: 'Whitespace id'},
        {id: '\u0085', name: 'Next line id'},
        {id: '', name: 'Blank id'},
        {id: '  padded  ', name: 'Padded id'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-work', name: 'Work', color: '#6B7280'},
    {id: ' \t', name: 'Whitespace id', color: '#6B7280'},
    {id: '\u0085', name: 'Next line id', color: '#6B7280'},
    {id: '', name: 'Blank id', color: '#6B7280'},
    {id: '  padded  ', name: 'Padded id', color: '#6B7280'},
  ]);
});

test('names Flutter FolderTabs empty GET names instead of omitting them', () => {
  const names = parseOmiFolderNames(
    JSON.stringify([
      {id: 'folder-work', name: 'Work'},
      {id: 'folder-empty', name: ' \t'},
      {id: 'folder-next', name: '\u0085'},
      {id: 'folder-blank', name: ''},
    ]),
  );
  expect(names.get('folder-work')).toBe('Work');
  expect(names.get('folder-empty')).toBe(' \t');
  expect(names.get('folder-next')).toBe('\u0085');
  expect(names.get('folder-blank')).toBe('');
});

test('names Flutter FolderTabs padded GET color as gray', () => {
  expect(omiFolderHexColor('#3b82f6')).toBe('#3B82F6');
  expect(omiFolderHexColor('00AA11')).toBe('#00AA11');
  expect(omiFolderHexColor('  #3b82f6  ')).toBeUndefined();
  expect(omiFolderHexColor('#3b82f6 ')).toBeUndefined();
  expect(omiFolderHexColor('\u0085#3b82f6')).toBeUndefined();
  expect(omiFolderHexColor('  00AA11  ')).toBeUndefined();
  expect(omiFolderHexColor(' \t')).toBeUndefined();
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-exact', name: 'Exact', color: '#3b82f6'},
        {id: 'folder-padded', name: 'Padded', color: '  #3b82f6  '},
        {id: 'folder-trailing', name: 'Trailing', color: '#3b82f6 '},
        {id: 'folder-next-line', name: 'Next line', color: '\u0085#3b82f6'},
        {id: 'folder-hashless-padded', name: 'Hashless padded', color: '  00AA11  '},
        {id: 'folder-hashless', name: 'Hashless', color: '00AA11'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-exact', name: 'Exact', color: '#3B82F6'},
    {id: 'folder-padded', name: 'Padded', color: '#6B7280'},
    {id: 'folder-trailing', name: 'Trailing', color: '#6B7280'},
    {id: 'folder-next-line', name: 'Next line', color: '#6B7280'},
    {id: 'folder-hashless-padded', name: 'Hashless padded', color: '#6B7280'},
    {id: 'folder-hashless', name: 'Hashless', color: '#00AA11'},
  ]);
});

test('names Flutter FolderTabs padded GET icon as default folder', () => {
  expect(omiFolderIconCopy('💼')).toBe('💼');
  expect(omiFolderIconCopy('🏠')).toBe('🏠');
  expect(omiFolderIconCopy('folder')).toBeUndefined();
  expect(omiFolderIconCopy('')).toBeUndefined();
  expect(omiFolderIconCopy(' \t')).toBeUndefined();
  expect(omiFolderIconCopy('  💼  ')).toBeUndefined();
  expect(omiFolderIconCopy('💼 ')).toBeUndefined();
  expect(omiFolderIconCopy('\u0085💼')).toBeUndefined();
  expect(omiFolderIconCopy('  folder  ')).toBeUndefined();
  expect(omiFolderIconCopy(undefined)).toBeUndefined();
  expect(() => omiFolderIconCopy(1)).toThrow();
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-exact', name: 'Exact', icon: '💼'},
        {id: 'folder-padded', name: 'Padded', icon: '  💼  '},
        {id: 'folder-trailing', name: 'Trailing', icon: '💼 '},
        {id: 'folder-next-line', name: 'Next line', icon: '\u0085💼'},
        {id: 'folder-word', name: 'Word', icon: 'folder'},
        {id: 'folder-house', name: 'House', icon: '🏠'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-exact', name: 'Exact', color: '#6B7280', icon: '💼'},
    {id: 'folder-padded', name: 'Padded', color: '#6B7280'},
    {id: 'folder-trailing', name: 'Trailing', color: '#6B7280'},
    {id: 'folder-next-line', name: 'Next line', color: '#6B7280'},
    {id: 'folder-word', name: 'Word', color: '#6B7280'},
    {id: 'folder-house', name: 'House', color: '#6B7280', icon: '🏠'},
  ]);
});

test('old folders name Flutter FolderTabs fromJson padded GET created_at instead of remapping to a folder chip', () => {
  const neighbor = {id: 'folder-kept', name: 'Neighbor', color: '#6B7280'};
  expect(
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          conversation_count: '99',
          order: '1',
        },
        {
          id: 'folder-json',
          name: 'Work',
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          conversation_count: 99,
          order: 1,
        },
        neighbor,
      ]),
    ),
  ).toEqual([
    {id: 'folder-work', name: 'Work', color: '#6B7280'},
    {id: 'folder-json', name: 'Work', color: '#6B7280'},
    neighbor,
  ]);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work'},
        neighbor,
      ]),
    ),
  ).toEqual([{id: 'folder-work', name: 'Work', color: '#6B7280'}, neighbor]);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          created_at: null,
          updated_at: null,
          conversation_count: null,
          order: null,
        },
        neighbor,
      ]),
    ),
  ).toEqual([{id: 'folder-work', name: 'Work', color: '#6B7280'}, neighbor]);
  for (const created_at of [
    '  2026-09-07T00:00:00.000Z  ',
    '2026-09-07T00:00:00.000Z ',
    '  2026-09-07T00:00:00.000Z',
    '2026-09-07T00:00:00.000Z\n',
    '\u00852026-09-07T00:00:00.000Z',
  ]) {
    expect(() =>
      parseOmiFolders(
        JSON.stringify([
          {id: 'folder-work', name: 'Work', created_at},
          neighbor,
        ]),
      ),
    ).toThrow('Omi folders are malformed');
  }
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          updated_at: '  2026-09-07T00:00:00.000Z  ',
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi folders are malformed');
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work', conversation_count: '  99  '},
        neighbor,
      ]),
    ),
  ).toThrow('Omi folders are malformed');
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work', order: '  1  '},
        neighbor,
      ]),
    ),
  ).toThrow('Omi folders are malformed');
});

test('old folders name Flutter Folder.fromGenerated type-wrong GET created_at instead of remapping to a folder chip', () => {
  const neighbor = {id: 'folder-kept', name: 'Neighbor', color: '#6B7280'};
  expect(
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          conversation_count: '99',
          order: '1',
        },
        neighbor,
      ]),
    ),
  ).toEqual([{id: 'folder-work', name: 'Work', color: '#6B7280'}, neighbor]);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {
          id: 'folder-work',
          name: 'Work',
          created_at: null,
          updated_at: null,
          conversation_count: null,
          order: null,
        },
        neighbor,
      ]),
    ),
  ).toEqual([{id: 'folder-work', name: 'Work', color: '#6B7280'}, neighbor]);
  for (const created_at of ['', 'not-a-date', 1, true, [], {}]) {
    expect(() =>
      parseOmiFolders(
        JSON.stringify([
          {id: 'folder-work', name: 'Work', created_at},
          neighbor,
        ]),
      ),
    ).toThrow('Omi folders are malformed');
  }
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work', updated_at: ''},
        neighbor,
      ]),
    ),
  ).toThrow('Omi folders are malformed');
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-work', name: 'Work', updated_at: 1},
        neighbor,
      ]),
    ),
  ).toThrow('Omi folders are malformed');
  for (const conversation_count of ['', 'abc', true, [], {}]) {
    expect(() =>
      parseOmiFolders(
        JSON.stringify([
          {id: 'folder-work', name: 'Work', conversation_count},
          neighbor,
        ]),
      ),
    ).toThrow('Omi folders are malformed');
  }
  expect(() =>
    parseOmiFolders(
      JSON.stringify([{id: 'folder-work', name: 'Work', order: ''}, neighbor]),
    ),
  ).toThrow('Omi folders are malformed');
  expect(() =>
    parseOmiFolders(
      JSON.stringify([{id: 'folder-work', name: 'Work', order: true}, neighbor]),
    ),
  ).toThrow('Omi folders are malformed');
});

test('parses GET omitted folder color as Flutter #6B7280', () => {
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
        {id: 'folder-omitted', name: 'Omitted'},
        {id: 'folder-plain', name: 'Plain', color: ' \t'},
        {id: 'folder-bad', name: 'Bad', color: 'blue'},
        {id: 'folder-short', name: 'Short', color: '#fff'},
        {id: 'folder-hashless', name: 'Hashless', color: '00AA11'},
        {id: 'folder-null', name: 'Null', color: null},
      ]),
    ),
  ).toEqual([
    {id: 'folder-work', name: 'Work', color: '#3B82F6', icon: '💼'},
    {id: 'folder-omitted', name: 'Omitted', color: '#6B7280'},
    {id: 'folder-plain', name: 'Plain', color: '#6B7280'},
    {id: 'folder-bad', name: 'Bad', color: '#6B7280'},
    {id: 'folder-short', name: 'Short', color: '#6B7280'},
    {id: 'folder-hashless', name: 'Hashless', color: '#00AA11'},
    {id: 'folder-null', name: 'Null'},
  ]);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-emoji', name: 'Home', icon: '🏠'},
        {id: 'folder-default', name: 'Inbox', icon: 'folder'},
        {id: 'folder-blank', name: 'Blank', icon: ' \t'},
        {id: 'folder-omitted', name: 'Omitted'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-emoji', name: 'Home', color: '#6B7280', icon: '🏠'},
    {id: 'folder-default', name: 'Inbox', color: '#6B7280'},
    {id: 'folder-blank', name: 'Blank', color: '#6B7280'},
    {id: 'folder-omitted', name: 'Omitted', color: '#6B7280'},
  ]);
  expect(() =>
    parseOmiFolders(
      JSON.stringify([{id: 'folder-bad-icon', name: 'Bad', icon: 1}]),
    ),
  ).toThrow();
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
  ).toEqual([{id: 'folder-work', name: 'Work', color: '#6B7280'}]);
});

test('keeps GET folders when a folder id exceeds 256', () => {
  const id = 'f'.repeat(257);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id, name: 'Work'},
        {id: 'folder-neighbor', name: 'Personal'},
      ]),
    ),
  ).toEqual([
    {id, name: 'Work', color: '#6B7280'},
    {id: 'folder-neighbor', name: 'Personal', color: '#6B7280'},
  ]);
});

test('keeps GET folders when a folder id exceeds 10000', () => {
  const id = 'f'.repeat(10001);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id, name: 'Work'},
        {id: 'folder-neighbor', name: 'Personal'},
      ]),
    ),
  ).toEqual([
    {id, name: 'Work', color: '#6B7280'},
    {id: 'folder-neighbor', name: 'Personal', color: '#6B7280'},
  ]);
});

test('fails closed when a folder id exceeds 1000000', () => {
  expect(() =>
    parseOmiFolders(
      JSON.stringify([
        {id: 'f'.repeat(1_000_001), name: 'Work'},
        {id: 'folder-neighbor', name: 'Personal'},
      ]),
    ),
  ).toThrow();
});

test('keeps GET folders when a name exceeds 10000', () => {
  const name = 'W'.repeat(10001);
  expect(
    parseOmiFolders(
      JSON.stringify([
        {id: 'folder-long', name},
        {id: 'folder-neighbor', name: 'Personal'},
      ]),
    ),
  ).toEqual([
    {id: 'folder-long', name, color: '#6B7280'},
    {id: 'folder-neighbor', name: 'Personal', color: '#6B7280'},
  ]);
});

test('does not omit neighboring GET folders when the catalogue exceeds 1000', () => {
  const rows = Array.from({length: 1001}, (_, index) => ({
    id: `folder-${index}`,
    name: `Folder ${index}`,
  }));
  const folders = parseOmiFolders(JSON.stringify(rows));
  expect(folders[0]).toEqual({
    id: 'folder-0',
    name: 'Folder 0',
    color: '#6B7280',
  });
  expect(folders[1000]).toEqual({
    id: 'folder-1000',
    name: 'Folder 1000',
    color: '#6B7280',
  });
  expect(folders).toHaveLength(1001);
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
    {id: 'folder-work', name: 'Work', color: '#6B7280'},
    {id: 'folder-empty', name: ' \t', color: '#6B7280'},
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
    {id: 'folder-work', name: 'Work', color: '#6B7280'},
  ]);
  request.mockResolvedValueOnce({id: 'folders', status: 404, body: null});
  expect(await loadOmiFolderNames(backend)).toEqual([]);
  request.mockResolvedValueOnce({id: 'folders', status: 200, body: '{'});
  await expect(loadOmiFolderNames(backend)).rejects.toThrow();
});

test('loadOmiFolder names a resolved GET folder color and omits misses', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {id: 'folder-work', name: 'Work', color: '#3B82F6', icon: '💼'},
      {id: 'folder-empty', name: ' \t', color: '#EF4444'},
      {id: ' \t', name: 'Whitespace id', color: '#10B981'},
      {id: '', name: 'Blank id'},
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiFolder(backend, 'folder-work')).toEqual({
    id: 'folder-work',
    name: 'Work',
    color: '#3B82F6',
    icon: '💼',
  });
  expect(await loadOmiFolder(backend, 'folder-empty')).toEqual({
    id: 'folder-empty',
    name: ' \t',
    color: '#EF4444',
  });
  expect(await loadOmiFolder(backend, ' \t')).toEqual({
    id: ' \t',
    name: 'Whitespace id',
    color: '#10B981',
  });
  expect(await loadOmiFolder(backend, '')).toEqual({
    id: '',
    name: 'Blank id',
    color: '#6B7280',
  });
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

test('old folders name Flutter FolderProvider fromJson padded GET created_at instead of empty folder chips', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {
        id: 'folder-work',
        name: 'Neighbor',
        created_at: '  2026-09-07T00:00:00.000Z  ',
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiFolderNames(backend)).rejects.toThrow(
    'Omi folders are malformed',
  );
  await expect(loadOmiFolder(backend, 'folder-work')).rejects.toThrow(
    'Omi folders are malformed',
  );
  await expect(loadOmiFolderName(backend, 'folder-work')).rejects.toThrow(
    'Omi folders are malformed',
  );
});

test('old folders name Flutter Folder.fromGenerated type-wrong GET created_at instead of empty folder chips', async () => {
  const request = jest.fn(async () => ({
    id: 'folders',
    status: 200,
    body: JSON.stringify([
      {
        id: 'folder-work',
        name: 'Neighbor',
        created_at: 1,
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiFolderNames(backend)).rejects.toThrow(
    'Omi folders are malformed',
  );
  await expect(loadOmiFolder(backend, 'folder-work')).rejects.toThrow(
    'Omi folders are malformed',
  );
  await expect(loadOmiFolderName(backend, 'folder-work')).rejects.toThrow(
    'Omi folders are malformed',
  );
});
