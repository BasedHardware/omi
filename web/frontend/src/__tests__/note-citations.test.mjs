import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { repairNoteCitations } from '@omi/note-shared/note-citations.mjs';
const contract = JSON.parse(
  readFileSync(
    new URL('../../../../contracts/note_citation_contract.json', import.meta.url),
  ),
);
for (const item of contract.cases) {
  test(item.name, () => {
    const result = repairNoteCitations(item.input, item.known_ids ?? contract.known_ids);
    assert.equal(result.text, item.output);
    assert.deepEqual(result.sourceIDs, item.source_ids);
    assert.equal(
      repairNoteCitations(result.text, item.known_ids ?? contract.known_ids).text,
      item.output,
    );
  });
}

test('a long unclosed backtick run stays text and code spans stay protected', () => {
  // The former single code regex backtracked quadratically on this shape.
  const run = 'x' + '`'.repeat(200000);
  assert.equal(repairNoteCitations(`${run} s01234`, ['s01234']).text, run);
  assert.equal(repairNoteCitations(`${run}\nFact [s01234].`, ['s01234']).text, `${run}\nFact.`);
  // At a line start the same run opens a fence, which protects the rest of the note.
  const fence = '`'.repeat(200000) + '\n[s01234]';
  assert.equal(repairNoteCitations(fence, ['s01234']).text, fence);
  assert.equal(
    repairNoteCitations('```\n[s01234]\n```\nFact [s01234].', ['s01234']).text,
    '```\n[s01234]\n```\nFact.',
  );
});

test('thousands of protected units restore exactly, including code nested in a link', () => {
  // Keys used to grow with the unit count and restore once per unit: quadratic.
  const many = Array.from({ length: 3000 }, (_, i) => `\`c${i}\` [s01234]`).join(' ');
  const kept = Array.from({ length: 3000 }, (_, i) => `\`c${i}\``).join(' ');
  assert.equal(repairNoteCitations(many, ['s01234']).text, kept);
  assert.deepEqual(repairNoteCitations('See [`x`](https://e.com) [s01234].', ['s01234']), {
    text: 'See [`x`](https://e.com).',
    sourceIDs: ['s01234'],
  });
});
