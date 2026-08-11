import { describe, it, expect } from 'vitest';
import { restingMode } from '@/lib/homeStage';

/**
 * Guards the rule that makes Home the only chat surface: an account with
 * history opens in the transcript, an empty one opens on the hub. Ported from
 * desktop's `HomeStagePresentation.restingMode`, so these cases match the
 * macOS app's.
 */
describe('restingMode', () => {
  it('rests on the hub for an account with no history', () => {
    expect(
      restingMode({ isLoading: false, hasMeaningfulHistory: false, isStreaming: false }),
    ).toBe('hub');
  });

  it('opens straight into chat when history exists', () => {
    expect(
      restingMode({ isLoading: false, hasMeaningfulHistory: true, isStreaming: false }),
    ).toBe('chat');
  });

  it('holds the hub while history is still loading', () => {
    // A stale count during the fetch would otherwise flash an empty transcript.
    expect(
      restingMode({ isLoading: true, hasMeaningfulHistory: true, isStreaming: false }),
    ).toBe('hub');
  });

  it('moves to chat on the first send, before any message is stored', () => {
    expect(
      restingMode({ isLoading: false, hasMeaningfulHistory: false, isStreaming: true }),
    ).toBe('chat');
  });
});
