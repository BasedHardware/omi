import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

import 'desktop_conversation_detail_page.dart';

class DesktopConversationDetailWrapper extends StatelessWidget {
  final ServerConversation conversation;
  final int conversationIndex;
  final DateTime selectedDate;

  const DesktopConversationDetailWrapper({
    super.key,
    required this.conversation,
    required this.conversationIndex,
    required this.selectedDate,
  });

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProxyProvider2<ConversationProvider, AppProvider, ConversationDetailProvider>(
      create: (context) {
        var provider = ConversationDetailProvider();
        provider.updateConversation(conversation.id, selectedDate);
        return provider;
      },
      update: (context, conversationProvider, appProvider, previous) {
        if (previous == null) {
          var provider = ConversationDetailProvider();
          provider.conversationProvider = conversationProvider;
          provider.appProvider = appProvider;
          provider.updateConversation(conversation.id, selectedDate);
          return provider;
        }
        previous.conversationProvider = conversationProvider;
        previous.appProvider = appProvider;
        return previous;
      },
      child: DesktopConversationDetailPage(conversation: conversation),
    );
  }
}
