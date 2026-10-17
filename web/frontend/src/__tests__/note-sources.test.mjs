import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolvableNoteSources } from '@omi/note-shared/note-sources.mjs';
import { repairNoteCitations } from '@omi/note-shared/note-citations.mjs';

test('source chips resolve typed provenance in first-mention order without exposing unknown IDs', () => {
  assert.deepEqual(resolvableNoteSources(['absent', 's2', 's1', 's2'], ['s1', 's2']), ['s2', 's1']);
  assert.deepEqual(resolvableNoteSources(['absent'], ['s1']), []);
  assert.deepEqual(resolvableNoteSources(undefined, ['s1']), []);
});

test('legacy citation repair never grants chip provenance', () => {
  const legacy = { body_markdown: 'Decision. [s1] []', source_segment_ids: [] };
  assert.equal(repairNoteCitations(legacy.body_markdown, ['s1']).text, 'Decision.');
  assert.deepEqual(resolvableNoteSources(legacy.source_segment_ids, ['s1']), []);
});
