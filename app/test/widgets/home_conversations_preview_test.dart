import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  testWidgets('home conversation preview shows the three newest filtered conversations', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);

    final today = DateTime.now();
    final yesterday = today.subtract(const Duration(days: 1));
    final conversations = [
      _conversation('newest', 'Newest', today),
      _conversation('middle', 'Middle', today.subtract(const Duration(hours: 1))),
      _conversation('yesterday', 'Yesterday', yesterday),
      _conversation('older', 'Older', yesterday.subtract(const Duration(days: 1))),
    ];
    provider.conversations = conversations;
    provider.groupedConversations = {
      DateTime(yesterday.year, yesterday.month, yesterday.day): [conversations[2], conversations[3]],
      DateTime(today.year, today.month, today.day): [conversations[0], conversations[1]],
    };

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider.value(
          value: provider,
          child: Scaffold(
            body: CustomScrollView(slivers: [HomeConversationsPreview(conversationProvider: provider)]),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(ConversationListItem), findsNWidgets(3));
    expect(find.text('Newest'), findsOneWidget);
    expect(find.text('Middle'), findsOneWidget);
    expect(find.text('Yesterday'), findsOneWidget);
    expect(find.text('Older'), findsNothing);
  });
}

ServerConversation _conversation(String id, String title, DateTime createdAt) {
  return ServerConversation(
    id: id,
    createdAt: createdAt,
    structured: Structured(title, 'Overview', emoji: '🧠'),
  );
}
