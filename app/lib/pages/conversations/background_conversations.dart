import 'package:omi/backend/schema/conversation.dart';

/// Whether Home leaves [conversation] to its day's recap instead of giving it a row (David
/// 2026-10-23). Older model votes cannot hide owner speech or unavailable speaker
/// resolution. Unknown identity stays visible; the backend finalizes new votes
/// against current speaker evidence. Search, folders, starred and chat still reach it.
bool leftToDailyRecap(ServerConversation conversation) =>
    conversation.structured.isBackground &&
    conversation.speakerResolution?.countable == true &&
    !conversation.transcriptSegments.any((segment) => segment.isUser) &&
    conversation.status == ConversationStatus.completed &&
    !conversation.starred &&
    !conversation.isLocked &&
    !conversation.discarded;
