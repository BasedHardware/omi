import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  presentableNoteSection,
  presentableNoteStructured,
  presentableNoteTitle,
  resolvableNoteSources,
} from '@omi/note-shared/note-sources.mjs';

test('source chips resolve typed provenance in first-mention order without exposing unknown IDs', () => {
  assert.deepEqual(resolvableNoteSources(['absent', 's2', 's1', 's2'], ['s1', 's2']), [
    's2',
    's1',
  ]);
  assert.deepEqual(resolvableNoteSources(['absent'], ['s1']), []);
  assert.deepEqual(resolvableNoteSources(undefined, ['s1']), []);
});

test('inline citations the repair removes become chips, matching macOS', () => {
  // A legacy section whose only evidence is an inline bracket must not lose its
  // transcript pointer when the bracket is cleaned out of the prose.
  const legacy = {
    heading: 'Plan [s2]',
    body_markdown: 'Decision. [s1] []',
    source_segment_ids: [],
  };
  const section = presentableNoteSection(legacy, ['s1', 's2']);
  assert.equal(section.heading, 'Plan');
  assert.equal(section.body_markdown, 'Decision.');
  assert.deepEqual(section.source_segment_ids, ['s2', 's1']);
});

test('typed provenance keeps first place and unresolvable IDs never become chips', () => {
  const section = presentableNoteSection(
    { body_markdown: 'Fact (s1; s3).', source_segment_ids: ['gone', 's3'] },
    ['s1', 's3'],
  );
  assert.equal(section.body_markdown, 'Fact.');
  assert.deepEqual(section.source_segment_ids, ['s3', 's1']);
  // Stored IDs outside the loaded transcript are still cleaned from prose but get no chip.
  const stale = presentableNoteSection(
    { body_markdown: 'Fact [gone].', source_segment_ids: ['gone'] },
    ['s1'],
  );
  assert.equal(stale.body_markdown, 'Fact.');
  assert.deepEqual(stale.source_segment_ids, []);
});

test('derived share surfaces read repaired title, overview and sections', () => {
  const structured = presentableNoteStructured(
    {
      title: 'Kickoff [s1]',
      overview: 'Speaker_00: Plan agreed. (s1)',
      sections: [{ heading: 'Decision', body_markdown: '- Ship it [s1]' }],
      meeting_type: 'standup',
    },
    ['s1'],
  );
  assert.equal(structured.title, 'Kickoff');
  assert.equal(structured.overview, 'Plan agreed.');
  assert.equal(structured.sections[0].body_markdown, '- Ship it');
  assert.deepEqual(structured.sections[0].source_segment_ids, ['s1']);
  assert.equal(structured.meeting_type, 'standup');
  assert.equal(presentableNoteStructured(undefined, ['s1']), undefined);
});

test('titles keep ordinary bracketed words and lose only citation-shaped units', () => {
  const cases = [
    ['Project [Q3]', [], 'Project [Q3]'],
    ['Q3 Review [2024]', [], 'Q3 Review [2024]'],
    ['Notes [v2] [s01234]', [], 'Notes [v2]'],
    ['Kickoff [s01234]', ['s01234'], 'Kickoff'],
    ['Recap [abc]', ['abc'], 'Recap'],
    ['Recap [Speaker 1]', [], 'Recap'],
    ['Speaker_00 recap', [], 'recap'],
    ['Sync [443191dc-8b75-4451-9d72-27c449b9ea45]', [], 'Sync'],
    ['Plan [s01234, Q3]', [], 'Plan [s01234, Q3]'],
    ['Mixed [Q3] text s01234', ['s01234'], 'Mixed [Q3] text'],
    ['[s01234]', [], ''],
    ['Project [Q3] \uE012', [], 'Project [Q3] \uE012'],
    ['[Project [s01234]]', [], '[Project [s01234]]'],
    ['[Project [s01234] notes', [], '[Project notes'],
    ['Plan ] [Q3] [s01234', [], 'Plan ] [Q3] [s01234'],
    ['Link [x](https://e.com) [s01234]', [], 'Link [x](https://e.com)'],
  ];
  for (const [input, ids, expected] of cases) {
    assert.equal(presentableNoteTitle(input, ids), expected, input);
  }
  const many = Array(5000).fill('[Q3]').join(' ');
  assert.equal(presentableNoteTitle(`${many} [s01234]`), many);
});
