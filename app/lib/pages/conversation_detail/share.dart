import 'dart:ui';

import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/share_links.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Opens the system share sheet with the conversation's public link. Resolves with the platform's
/// result: [ShareResultStatus.dismissed] means the reader closed the sheet without sharing
/// (reported on iOS and Android 5.1+); [ShareResultStatus.unavailable] means the platform could
/// not tell.
Future<ShareResult> shareConversationLink(ServerConversation conversation, {Rect? sharePositionOrigin}) async {
  final subject = conversation.structured.title;
  final sid = newShareId();
  final outcome = await SharePlus.instance.share(
    ShareParams(
      text: conversationShareUrl(conversation.id, sid: sid),
      subject: subject.isEmpty ? null : subject,
      sharePositionOrigin: sharePositionOrigin,
    ),
  );
  PlatformManager.instance.analytics.conversationShared(
    conversation: conversation,
    shareMethod: 'url_share',
    shareId: sid,
    targetApp: outcome.status == ShareResultStatus.success ? shareTargetApp(outcome.raw) : null,
    shareStatus: outcome.status.name,
  );
  return outcome;
}
