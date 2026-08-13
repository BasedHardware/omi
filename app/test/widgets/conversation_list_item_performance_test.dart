import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('conversation rows are isolated behind a repaint boundary', (tester) async {
    final conversation = ServerConversation(
      id: 'c1',
      createdAt: DateTime.utc(2020),
      structured: Structured('A conversation', 'Overview'),
    );
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    )..conversations = [conversation];
    addTearDown(provider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<ConversationProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: ConversationListItem(conversation: conversation, date: DateTime.utc(2020), conversationIdx: 0),
          ),
        ),
      ),
    );

    expect(
      find.ancestor(of: find.byType(ConversationListItem), matching: find.byType(RepaintBoundary)),
      findsAtLeastNWidgets(1),
    );

    provider.enterSelectionMode();
    await tester.pump();
    expect(find.byType(ConversationListItem), findsOneWidget);
  });
}
