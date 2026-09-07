import { describe, expect, it } from 'vitest';
import { prependOrReplaceById } from '../actionItemList';

describe('prependOrReplaceById', () => {
  it('prepends a new id', () => {
    const existing = { id: 'old', description: '123' };
    const created = { id: 'new', description: '123' };
    expect(prependOrReplaceById([existing], created)).toEqual([created, existing]);
  });

  it('replaces an existing id instead of cloning the row', () => {
    const first = { id: 'same', description: '123', due_at: '2026-01-01' };
    const replay = { id: 'same', description: '123', due_at: '2026-01-02' };
    expect(prependOrReplaceById([first], replay)).toEqual([replay]);
  });
});
