import {
  appChangelogHeading,
  appChangelogLoadedHeading,
  appChangelogsLoadErrorCopy,
  loadOmiAppChangelogs,
  parseOmiAppChangelogs,
} from './legacyOmiAppChangelogs';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET app changelogs with Flutter omitted-icon ✨', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
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
              {title: 'Empty icon', description: '', icon: ''},
              {title: 'Null icon', description: '', icon: null},
            ],
          },
        },
        {
          id: 'ann-feature',
          type: 'feature',
          created_at: '2026-09-09T12:00:00.000Z',
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
      copy: '✨ ·    · Hidden empty title.',
    },
    {
      key: 'ann-1:2',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay ·  \t',
    },
    {
      key: 'ann-1:3',
      title: "What's New in 1.2.0",
      copy: ' · Empty icon · ',
    },
    {
      key: 'ann-1:4',
      title: "What's New in 1.2.0",
      copy: '✨ · Null icon · ',
    },
  ]);
  expect(appChangelogHeading('')).toBe("What's New");
  expect(appChangelogHeading('  ')).toBe("What's New");
  expect(appChangelogsLoadErrorCopy()).toBe('Failed to load changelogs');
});

test('names Flutter ChangelogSheet empty GET icons instead of omitting the prefix', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty-icon',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {
            changes: [
              {title: 'Empty icon', description: 'Kept description.', icon: ''},
              {
                title: 'Whitespace icon',
                description: 'Kept description.',
                icon: ' \t',
              },
            ],
          },
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-empty-icon:0',
      title: "What's New in 1.2.0",
      copy: ' · Empty icon · Kept description.',
    },
    {
      key: 'ann-empty-icon:1',
      title: "What's New in 1.2.0",
      copy: ' \t · Whitespace icon · Kept description.',
    },
  ]);
});

test('names Flutter ChangelogSheet empty GET app_version as What\'s New in ', () => {
  expect(appChangelogLoadedHeading('')).toBe("What's New in ");
  expect(appChangelogLoadedHeading('  ')).toBe("What's New in   ");
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty-version',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: ' \t',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
        {
          id: 'ann-omitted-version',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-empty-version:0',
      title: "What's New in  \t",
      copy: '✨ · Offline replay · ',
    },
    {
      key: 'ann-omitted-version:0',
      title: "What's New in ",
      copy: '✨ · Faster sync · ',
    },
  ]);
});

test('names Flutter ChangelogSheet padded GET app_version instead of remapping to a version chip', () => {
  expect(appChangelogLoadedHeading('1.2.0')).toBe("What's New in 1.2.0");
  expect(appChangelogLoadedHeading('1.2.0 ')).toBe("What's New in 1.2.0 ");
  expect(appChangelogLoadedHeading('  1.2.0  ')).toBe(
    "What's New in   1.2.0  ",
  );
  expect(appChangelogLoadedHeading('\u00851.2.0')).toBe(
    "What's New in \u00851.2.0",
  );
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-exact',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Exact version', description: ''}]},
        },
        {
          id: 'ann-padded',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '  1.2.0  ',
          content: {changes: [{title: 'Padded version', description: ''}]},
        },
        {
          id: 'ann-trail',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0 ',
          content: {changes: [{title: 'Trailing version', description: ''}]},
        },
        {
          id: 'ann-next',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '\u00851.2.0',
          content: {changes: [{title: 'Next-line version', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-exact:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Exact version · ',
    },
    {
      key: 'ann-padded:0',
      title: "What's New in   1.2.0  ",
      copy: '✨ · Padded version · ',
    },
    {
      key: 'ann-trail:0',
      title: "What's New in 1.2.0 ",
      copy: '✨ · Trailing version · ',
    },
    {
      key: 'ann-next:0',
      title: "What's New in \u00851.2.0",
      copy: '✨ · Next-line version · ',
    },
  ]);
});

test('names Flutter ChangelogSheet empty GET ids instead of omitting them', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: ' \t',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.3.0',
          content: {changes: [{title: 'Whitespace id', description: ''}]},
        },
        {
          id: '\u0085',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.4.0',
          content: {changes: [{title: 'Next line id', description: ''}]},
        },
        {
          id: '',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.5.0',
          content: {changes: [{title: 'Blank id', description: ''}]},
        },
        {
          id: '  padded  ',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.6.0',
          content: {changes: [{title: 'Padded id', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-1:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: ' \t:0',
      title: "What's New in 1.3.0",
      copy: '✨ · Whitespace id · ',
    },
    {
      key: '\u0085:0',
      title: "What's New in 1.4.0",
      copy: '✨ · Next line id · ',
    },
    {
      key: ':0',
      title: "What's New in 1.5.0",
      copy: '✨ · Blank id · ',
    },
    {
      key: '  padded  :0',
      title: "What's New in 1.6.0",
      copy: '✨ · Padded id · ',
    },
  ]);
});

test('names Flutter ChangelogSheet empty GET change titles instead of omitting the announcement', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {
            changes: [
              {title: '  ', description: 'Hidden empty title.'},
              {title: '', description: ''},
              {title: '\u0085', description: 'Next line title.'},
              {title: '  padded  ', description: ''},
            ],
          },
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-empty:0',
      title: "What's New in 1.2.0",
      copy: '✨ ·    · Hidden empty title.',
    },
    {
      key: 'ann-empty:1',
      title: "What's New in 1.2.0",
      copy: '✨',
    },
    {
      key: 'ann-empty:2',
      title: "What's New in 1.2.0",
      copy: '✨ · \u0085 · Next line title.',
    },
    {
      key: 'ann-empty:3',
      title: "What's New in 1.2.0",
      copy: '✨ ·   padded   · ',
    },
  ]);
});

test('names Flutter ChangelogSheet empty GET descriptions instead of omitting the subtitle', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty-desc',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {
            changes: [
              {title: 'Offline replay', description: ''},
              {title: 'Whitespace description', description: ' \t'},
              {title: 'Next line description', description: '\u0085'},
            ],
          },
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-empty-desc:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
    {
      key: 'ann-empty-desc:1',
      title: "What's New in 1.2.0",
      copy: '✨ · Whitespace description ·  \t',
    },
    {
      key: 'ann-empty-desc:2',
      title: "What's New in 1.2.0",
      copy: '✨ · Next line description · \u0085',
    },
  ]);
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
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.0.0',
          content: {changes: [{title: 1, description: 'nope'}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
        {
          id: 'ann-bad-changes',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.3.0',
          content: {changes: 'fast'},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-1',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
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
          created_at: '2026-09-09T12:00:00.000Z',
          content: {changes: 'fast'},
        },
      ]),
    ),
  ).toEqual([]);
});

test('keeps GET app changelogs when the announcement list exceeds 10', () => {
  const rows = Array.from({length: 11}, (_, index) => ({
    id: `ann-${index}`,
    type: 'changelog',
    created_at: '2026-09-09T12:00:00.000Z',
    app_version: '1.2.0',
    content: {changes: [{title: `Change ${index}`, description: ''}]},
  }));
  expect(parseOmiAppChangelogs(JSON.stringify(rows))).toEqual(
    Array.from({length: 5}, (_, index) => ({
      key: `ann-${index}:0`,
      title: "What's New in 1.2.0",
      copy: `✨ · Change ${index} · `,
    })),
  );
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
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.4.0',
          content: {changes},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    ...changes.map((change, index) => ({
      key: `ann-long:${index}`,
      title: "What's New in 1.4.0",
      copy: `✨ · ${change.title} · `,
    })),
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
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
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.5.0',
          content: {
            changes: [{title: 'Faster sync', description: '', icon}],
          },
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-icon:0',
      title: "What's New in 1.5.0",
      copy: `${icon} · Faster sync · `,
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('keeps GET app changelog title, description, or icon longer than 10000', () => {
  const title = 'T'.repeat(10001);
  const description = 'D'.repeat(10001);
  const icon = 'I'.repeat(10001);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-long-copy',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.6.0',
          content: {
            changes: [{title, description, icon}],
          },
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-long-copy:0',
      title: "What's New in 1.6.0",
      copy: `${icon} · ${title} · ${description}`,
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
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
          created_at: '2026-09-09T12:00:00.000Z',
          app_version,
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-version:0',
      title: `What's New in ${app_version}`,
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('keeps GET app changelog app_version longer than 10000', () => {
  const app_version = 'x'.repeat(10001);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-version',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version,
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-version:0',
      title: `What's New in ${app_version}`,
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('names Flutter ChangelogSheet unknown GET type instead of keeping neighbors', () => {
  const unknown = 'f'.repeat(65);
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-unknown',
          type: unknown,
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-long',
          type: 'f'.repeat(10001),
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty',
          type: '',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-whitespace',
          type: ' \t',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-padded',
          type: ' changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
});

test('names Flutter ChangelogSheet fromJson invalid created_at instead of undated success', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const neighbor = {
    id: 'ann-good',
    type: 'changelog',
    created_at: createdAt,
    app_version: '1.2.0',
    content: {changes: [{title: 'Offline replay', description: ''}]},
  };
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-null',
          type: 'changelog',
          created_at: null,
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-omitted',
          type: 'changelog',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-undated',
          type: 'changelog',
          created_at: 'not-a-date',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty',
          type: 'changelog',
          created_at: '',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-space',
          type: 'changelog',
          created_at: ' \t',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-feature',
          type: 'feature',
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
});

test('names Flutter ChangelogSheet fromJson missing GET content instead of keeping neighbors', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const neighbor = {
    id: 'ann-good',
    type: 'changelog',
    created_at: createdAt,
    app_version: '1.2.0',
    content: {changes: [{title: 'Offline replay', description: ''}]},
  };
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-feature',
          type: 'feature',
          created_at: createdAt,
          app_version: '1.2.0',
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          type: 'feature',
          created_at: createdAt,
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: '',
          type: 'feature',
          created_at: createdAt,
          app_version: '1.2.0',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('names Flutter ChangelogSheet fromGenerated unknown GET trigger instead of keeping neighbors', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const neighbor = {
    id: 'ann-good',
    type: 'changelog',
    created_at: createdAt,
    app_version: '1.2.0',
    content: {changes: [{title: 'Offline replay', description: ''}]},
  };
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-trigger',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: 'bogus'},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-empty-trigger',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: ''},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-space-trigger',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: ' \t'},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-null-trigger',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: null},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-feature',
          type: 'feature',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: 'bogus'},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-targeting',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: 'nope',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-expires',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          display: {expires_at: 'not-a-date'},
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
});

test('names Flutter ChangelogSheet fromJson invalid GET active instead of keeping neighbors', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const neighbor = {
    id: 'ann-good',
    type: 'changelog',
    created_at: createdAt,
    app_version: '1.2.0',
    content: {changes: [{title: 'Offline replay', description: ''}]},
  };
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-feature',
          type: 'feature',
          created_at: createdAt,
          app_version: '1.2.0',
          active: 'yes',
          content: {title: 'Feature'},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-null-active',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          active: null,
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-firmware',
          type: 'feature',
          created_at: createdAt,
          firmware_version: 12,
          content: {title: 'Feature'},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-models',
          type: 'announcement',
          created_at: createdAt,
          device_models: 'omi',
          content: {title: 'Note', body: 'Hi'},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-expires',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          expires_at: 'not-a-date',
          content: {changes: [{title: 'Skip me', description: ''}]},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-version',
          type: 'feature',
          created_at: createdAt,
          app_version: 1,
          content: {title: 'Feature'},
        },
        neighbor,
      ]),
    ),
  ).toThrow('Omi app changelogs are malformed');
});

test('keeps GET app changelogs when fromJson optional announcement extras are omitted or valid', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const content = {changes: [{title: 'Faster sync', description: ''}]};
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-active',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          active: true,
          firmware_version: '1.0.0',
          device_models: ['omi'],
          expires_at: createdAt,
          content,
        },
        {
          id: 'ann-null-extras',
          type: 'changelog',
          created_at: createdAt,
          app_version: null,
          firmware_version: null,
          device_models: null,
          expires_at: null,
          content,
        },
        {
          id: 'ann-feature',
          type: 'feature',
          created_at: createdAt,
          active: false,
          app_version: '',
          firmware_version: ' \t',
          device_models: [''],
          expires_at: '2026-04-01T12:00:00+00',
          content: {title: 'Feature'},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-active:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-null-extras:0',
      title: "What's New in ",
      copy: '✨ · Faster sync · ',
    },
  ]);
});

test('keeps GET app changelogs when targeting trigger is omitted or a Flutter enum value', () => {
  const createdAt = '2026-09-09T12:00:00.000Z';
  const content = {changes: [{title: 'Faster sync', description: ''}]};
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-default',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {},
          content,
        },
        {
          id: 'ann-upgrade',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: 'version_upgrade'},
          content,
        },
        {
          id: 'ann-immediate',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: 'immediate'},
          content,
        },
        {
          id: 'ann-firmware',
          type: 'changelog',
          created_at: createdAt,
          app_version: '1.2.0',
          targeting: {trigger: 'firmware_upgrade'},
          display: {expires_at: null, start_at: createdAt, priority: 0},
          content,
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-default:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-upgrade:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-immediate:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-firmware:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
  ]);
});

test('keeps GET app changelogs when created_at exceeds 10000', () => {
  const longCreatedAt = `2026-04-01T12:00:00.${'0'.repeat(9980)}Z`;
  expect(longCreatedAt.length).toBe(10001);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-long',
          type: 'changelog',
          created_at: longCreatedAt,
          app_version: '1.2.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-long:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('keeps GET app changelogs when created_at uses hour-only offsets Dart DateTime.tryParse accepts', () => {
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'ann-hour',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00+00',
          app_version: '1.2.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: 'ann-hour:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('keeps GET app changelogs when an announcement id exceeds 256', () => {
  const id = 'a'.repeat(257);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id,
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.0.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: `${id}:0`,
      title: "What's New in 1.0.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('keeps GET app changelogs when an announcement id exceeds 10000', () => {
  const id = 'a'.repeat(10001);
  expect(
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id,
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.0.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
        },
      ]),
    ),
  ).toEqual([
    {
      key: `${id}:0`,
      title: "What's New in 1.0.0",
      copy: '✨ · Faster sync · ',
    },
    {
      key: 'ann-good:0',
      title: "What's New in 1.2.0",
      copy: '✨ · Offline replay · ',
    },
  ]);
});

test('fails closed when an announcement id exceeds 1000000', () => {
  expect(() =>
    parseOmiAppChangelogs(
      JSON.stringify([
        {
          id: 'a'.repeat(1_000_001),
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.0.0',
          content: {changes: [{title: 'Faster sync', description: ''}]},
        },
        {
          id: 'ann-good',
          type: 'changelog',
          created_at: '2026-09-09T12:00:00.000Z',
          app_version: '1.2.0',
          content: {changes: [{title: 'Offline replay', description: ''}]},
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
        created_at: '2026-09-09T12:00:00.000Z',
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
      copy: '✨ · New Home · A calmer capture card.',
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
    status: 500,
    body: '{"error":"internal"}',
  });
  expect(await loadOmiAppChangelogs(backend)).toEqual([]);
});

test('loadOmiAppChangelogs names malformed GET instead of empty success', async () => {
  const request = jest.fn(async () => ({
    id: 'changelogs',
    status: 200,
    body: JSON.stringify({changes: []}),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiAppChangelogs(backend)).rejects.toThrow(
    'Omi app changelogs are malformed',
  );
});
