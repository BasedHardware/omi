import { describe, expect, it } from 'vitest';
import contract from '../../../../../contracts/note_citation_contract.json';
import { repairNoteCitations } from '../../../../shared/note-citations.mjs';

describe('hand-authored note citation contract', () => {
  for (const item of contract.cases) {
    it(item.name, () => {
      const result = repairNoteCitations(item.input, contract.known_ids);
      expect(result.text).toBe(item.output);
      expect(result.sourceIDs).toEqual(item.source_ids);
      expect(repairNoteCitations(result.text, contract.known_ids).text).toBe(item.output);
    });
  }
});
