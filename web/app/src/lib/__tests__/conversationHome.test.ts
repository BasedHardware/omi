import { describe, expect, it } from 'vitest';
import { conversationsForSurface } from '../conversationHome';
import type { Conversation } from '@/types/conversation';

describe('Home and Activity failure placement', () => {
  const rows = [
    { id: 'projected', status: 'processing', home_step: 'failed' },
    { id: 'terminal', status: 'failed' },
    { id: 'ready', status: 'completed' },
    { id: 'live', status: 'processing' },
  ] as Conversation[];
  it('puts every failure in exactly one surface', () => {
    expect(conversationsForSurface(rows, false, true).map((row) => row.id)).toEqual([
      'ready',
      'live',
    ]);
    expect(conversationsForSurface(rows, true, true).map((row) => row.id)).toEqual([
      'projected',
      'terminal',
    ]);
  });
  it('restores the complete previous Home on missing or failed confirmation', () => {
    expect(conversationsForSurface(rows, false, false)).toBe(rows);
    expect(conversationsForSurface(rows, true, false)).toEqual([]);
  });
});

// Noise is hidden from Home without becoming Activity attention by inference.
it('keeps projected noise off Home and out of failed Activity, with rollback', () => {
  const row = { id: 'noise', status: 'completed', home_step: 'noise' } as Conversation;
  expect(conversationsForSurface([row], false, true)).toEqual([]);
  expect(conversationsForSurface([row], true, true)).toEqual([]);
  expect(conversationsForSurface([row], false, false)).toEqual([row]);
});
