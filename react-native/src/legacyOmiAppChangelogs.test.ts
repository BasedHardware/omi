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
});

test('names neighboring GET changelogs when one announcement change cannot project', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-bad-title',
          type: 'changelog',
          app_version: '1.0.0',
          content: {changes: [{title: 1, description: 'nope'}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
        {
          id: 'ann-bad-changes',
          type: 'changelog',
          app_version: '1.3.0',
          content: {changes: 'fast'},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: 'Offline replay',
    },
  ]);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          content: {changes: [{title: 1, description: 'nope'}]},
        },
      ]),
    ),
  ).toEqual([]);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          content: {changes: 'fast'},
        },
      ]),
    ),
  ).toEqual([]);
});

test('keeps GET app changelog changes when more than 32', () => {
  const changes = Array.from({length: 33}, (_, index) => ({
    title: `Change ${index}`,
    description: '',
  }));
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-long',
          type: 'changelog',
          app_version: '1.4.0',
          content: {changes},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    ...changes.map((change, index) => ({
      key: `ann-long:${index}`,
      title: "What's New in 1.4.0",
      copy: change.title,
    })),
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: 'Offline replay',
    },
  ]);
});

test('keeps GET app changelog icon longer than 32', () => {
  const icon = 'x'.repeat(33);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-icon',
          type: 'changelog',
          app_version: '1.5.0',
          content: {
            changes: [{title: 'Faster sync', description: '', icon}],
          },
        },
        {
          id: 'ann-good',
          type: 'changelog',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-icon:0',
      title: "What's New in 1.5.0",
      copy: `${icon} · Faster sync`,
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: 'Offline replay',
    },
  ]);
});

test('keeps GET app changelog app_version longer than 64', () => {
  const app_version = 'x'.repeat(65);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-version',
          type: 'changelog',
          app_version,
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-version:0',
      title: `What's New in ${app_version}`,
      copy: 'Faster sync',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: 'Offline replay',
    },
  ]);
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
