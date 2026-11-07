import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_links.dart';

/// Updates a conversation's visibility; tests inject a stub.
@visibleForTesting
Future<bool> Function(String conversationId, {String visibility}) conversationShareVisibilityUpdater =
    setConversationVisibility;

/// Opens the system share sheet for a conversation link; tests inject a stub.
@visibleForTesting
Future<ShareResult> Function(ServerConversation conversation, {Rect? sharePositionOrigin}) conversationLinkSharer =
    shareConversationLink;

/// Opens the system share sheet with the conversation's public link. Resolves with the platform's
/// result: [ShareResultStatus.dismissed] means the reader closed the sheet without sharing
/// (reported on iOS and Android 5.1+); [ShareResultStatus.unavailable] means the platform could
/// not tell.
Future<ShareResult> shareConversationLink(ServerConversation conversation, {Rect? sharePositionOrigin}) async {
  // The share subject is a display surface: legacy titles lose citation debris (`[s01234]`).
  final subject = presentableConversationTitle(conversation);
  final sid = newShareId();
  final outcome = await SharePlus.instance.share(
    ShareParams(
      text: conversationShareUrl(conversation.id, sid: sid),
      subject: subject.isEmpty ? null : subject,
      sharePositionOrigin: sharePositionOrigin,
    ),
  );
  final analytics = PlatformManager.instance.analytics;
  final targetApp = outcome.status == ShareResultStatus.success ? shareTargetApp(outcome.raw) : null;
  analytics.track('Conversation Shared', properties: {
    ...analytics.getConversationEventProperties(conversation),
    'share_method': 'url_share',
    'share_id': sid,
    'share_status': outcome.status.name,
    if (targetApp != null) 'target_app': targetApp,
  });
  return outcome;
}
