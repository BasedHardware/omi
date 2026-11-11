export const MIN_CONVERSATION_DETAIL_WIDTH = 360;
export const MIN_CONVERSATION_GALLERY_WIDTH = 280;

export function resizeConversationDetailPanel(
  currentWidth: number,
  pointerDelta: number,
  containerWidth: number,
): number {
  const maximum = Math.max(
    MIN_CONVERSATION_DETAIL_WIDTH,
    containerWidth - MIN_CONVERSATION_GALLERY_WIDTH,
  );
  return Math.min(
    maximum,
    Math.max(MIN_CONVERSATION_DETAIL_WIDTH, currentWidth - pointerDelta),
  );
}
