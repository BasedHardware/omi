import 'package:omi/backend/schema/conversation.dart';

/// Whether Home leaves [conversation] to its day's recap instead of giving it a row (David
/// 2026-10-23): the notes pass called it background, and nothing the person did to it (a star, a
/// lock, unfinished processing) asks for a row of its own. Search, folders, starred and chat still
/// reach it.
bool leftToDailyRecap(ServerConversation conversation) =>
    conversation.structured.isBackground &&
    conversation.status == ConversationStatus.completed &&
    !conversation.starred &&
    !conversation.isLocked &&
    !conversation.discarded;
