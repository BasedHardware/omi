/// When a homepage processing card should warn that work looks stuck (#5481).
const Duration conversationProcessingTimeout = Duration(minutes: 2);

/// True once [processingStartedAt] is at least [conversationProcessingTimeout]
/// before [now]. Local placeholder rows (`id == '0'`) are never timed out —
/// they have no server conversation to retry yet.
bool isConversationProcessingTimedOut({
  required String conversationId,
  required DateTime processingStartedAt,
  required DateTime now,
  Duration timeout = conversationProcessingTimeout,
}) {
  if (conversationId == '0') return false;
  return !now.isBefore(processingStartedAt.add(timeout));
}
