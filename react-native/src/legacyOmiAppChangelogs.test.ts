import {
  appChangelogHeading,
  loadOmiAppChangelogs,
  parseOmiAppChangelogs,
} from './legacyOmiAppChangelogs';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET app changelogs without inventing a missing icon', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          app_version: '1.2.0',
          content: {
            title: 'Release notes',
            changes: [
              {
                title: 'Faster sync',
                description: 'Uploads finish sooner.',
                icon: '🚀',
              },
              {title: '  ', description: 'Hidden empty title.'},
              {title: 'Offline replay', description: ' \t'},
            ],
          },
        },
        {
          id: 'ann-feature',
          type: 'feature',
          app_version: '1.2.0',
          content: {
            title: 'Feature',
            changes: [{title: 'Skip me', description: ''}],
          },
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-1:0',
      title: "What's New in 1.2.0",
      copy: '🚀 · Faster sync · Uploads finish sooner.',
    },
    {
      key: 'ann-1:1',
      title: "What's New in 1.2.0",
      copy: 'Offline replay',
    },
  ]);
  expect(appChangelogHeading('')).toBe("What's New");
  expect(appChangelogHeading('  ')).toBe("What's New");
});

test('fails closed for malformed GET app changelogs', () => {
  expect(() => parseOmiAppChangelogs(JSON.stringify({}))).toThrow();
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          content: {changes: [{title: 1, description: 'nope'}]},
        },
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          content: {changes: 'fast'},
        },
      ]),
    ),
  ).toThrow();
});

test('loadOmiAppChangelogs names GET rows and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'changelogs',
    status: 200,
    body: JSON.stringify([
      {
        id: 'ann-1',
        type: 'changelog',
        app_version: '2.0.0',
        content: {
          changes: [{title: 'New Home', description: 'A calmer capture card.'}],
        },
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiAppChangelogs(backend)).toEqual([
    {
      key: 'ann-1:0',
      title: "What's New in 2.0.0",
      copy: 'New Home · A calmer capture card.',
    },
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/announcements/changelogs?limit=5',
  });
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].path.includes('dismiss'),
    ),
  ).toBe(false);
  expect(
    request.mock.calls.some(call => call[0].path.includes('/pending')),
  ).toBe(false);
  request.mockResolvedValue({id: 'changelogs', status: 404, body: null});
  expect(await loadOmiAppChangelogs(backend)).toEqual([]);
  request.mockResolvedValue({
    id: 'changelogs',
    status: 200,
    body: JSON.stringify({changes: []}),
  });
  expect(await loadOmiAppChangelogs(backend)).toEqual([]);
});
