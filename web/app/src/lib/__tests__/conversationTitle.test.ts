import { describe, expect, it } from 'vitest';
import { conversationDisplayTitle } from '../conversationTitle';

describe('conversationDisplayTitle', () => {
  it('repairs citation debris against the transcript', () => {
    expect(
      conversationDisplayTitle({
        structured: { title: 'Kickoff [s1]' },
        transcript_segments: [{ id: 's1' }],
      }),
    ).toBe('Kickoff');
  });

  it('strips speaker labels and ID-like brackets when the list payload has no transcript', () => {
    expect(
      conversationDisplayTitle({ structured: { title: 'Speaker_00 recap [s01234]' } }),
    ).toBe('recap');
  });

  it('keeps ordinary bracketed words in titles', () => {
    expect(conversationDisplayTitle({ structured: { title: 'Project [Q3]' } })).toBe(
      'Project [Q3]',
    );
    expect(
      conversationDisplayTitle({ structured: { title: 'Call [Kickoff] [s01234]' } }),
    ).toBe('Call [Kickoff]');
  });

  it('keeps ordinary titles and returns empty for a missing title', () => {
    expect(
      conversationDisplayTitle({ structured: { title: 'Q3 planning (draft)' } }),
    ).toBe('Q3 planning (draft)');
    expect(conversationDisplayTitle({ structured: null })).toBe('');
  });
});
