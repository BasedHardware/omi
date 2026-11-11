import { describe, expect, it } from 'vitest';
import {
  MIN_CONVERSATION_DETAIL_WIDTH,
  MIN_CONVERSATION_GALLERY_WIDTH,
  resizeConversationDetailPanel,
} from '@/lib/conversationPanelSizing';

describe('conversation detail panel sizing', () => {
  it('can expand past the previous fixed 720px ceiling', () => {
    expect(resizeConversationDetailPanel(720, -500, 1800)).toBe(1220);
  });

  it('keeps a compact gallery visible at the far-left stop', () => {
    expect(resizeConversationDetailPanel(720, -2000, 1800)).toBe(
      1800 - MIN_CONVERSATION_GALLERY_WIDTH,
    );
  });

  it('retains the minimum readable detail width when dragged right', () => {
    expect(resizeConversationDetailPanel(480, 1000, 1800)).toBe(
      MIN_CONVERSATION_DETAIL_WIDTH,
    );
  });
});
