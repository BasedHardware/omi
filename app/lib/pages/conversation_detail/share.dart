import 'dart:ui';

import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/share_links.dart';

/// Opens the system share sheet with the conversation's public link. Resolves with the platform's
/// result: [ShareResultStatus.dismissed] means the reader closed the sheet without sharing
/// (reported on iOS and Android 5.1+); [ShareResultStatus.unavailable] means the platform could
/// not tell.
Future<ShareResult> shareConversationLink(ServerConversation conversation, {Rect? sharePositionOrigin}) {
  final subject = conversation.structured.title;
  return SharePlus.instance.share(
    ShareParams(
      text: conversationShareUrl(conversation.id),
      subject: subject.isEmpty ? null : subject,
      sharePositionOrigin: sharePositionOrigin,
    ),
  );
}
