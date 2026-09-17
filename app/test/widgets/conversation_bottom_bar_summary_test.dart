import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

ServerConversation _conversation({required List<AppResponse> appResults}) {
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: Structured('Sprint sync', 'First-party overview.', emoji: '🧠'),
    appResults: appResults,
  );
}

ConversationDetailProvider _provider(ServerConversation conversation) {
  final provider = ConversationDetailProvider();
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

Future<void> _pumpBar(WidgetTester tester, ConversationDetailProvider provider) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: Scaffold(
          body: ConversationBottomBar(
            mode: ConversationBottomBarMode.detail,
            selectedTab: ConversationTab.summary,
            onTabSelected: (_) {},
            onStopPressed: () {},
            hasSegments: true,
            hasActionItems: false,
            conversation: provider.conversation,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('unattributed app output keeps Unknown App chrome in the summary pill', (tester) async {
    final provider = _provider(_conversation(appResults: [AppResponse('Imported app output.')]));
    addTearDown(provider.dispose);

    await _pumpBar(tester, provider);

    expect(find.text('Unknown ...'), findsOneWidget);
    expect(find.byIcon(Icons.apps_outlined), findsOneWidget);
    expect(find.text('Summary'), findsNothing);
  });
}
