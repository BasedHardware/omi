import 'dart:ui';

import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/schema/conversation.dart';

void shareConversationLink(ServerConversation conversation, {Rect? sharePositionOrigin}) {
  final content = 'https://h.omi.me/conversations/${conversation.id}';
  Share.share(content, subject: conversation.structured.title, sharePositionOrigin: sharePositionOrigin);
}
