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
    const result = repairNoteCitations(item.input, (item.known_ids ?? contract.known_ids));
    assert.equal(result.text, item.output);
    assert.deepEqual(result.sourceIDs, item.source_ids);
    assert.equal(repairNoteCitations(result.text, (item.known_ids ?? contract.known_ids)).text, item.output);
  });
}
