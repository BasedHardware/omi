export const RECORD_CONTROL_EDGE_OFFSET = 24;

export function getRecordControlRightOffset(
  isChatOpen: boolean,
  isNotificationOpen: boolean,
): number {
  return (
    RECORD_CONTROL_EDGE_OFFSET + (isChatOpen ? 404 : 0) + (isNotificationOpen ? 404 : 0)
  );
}
