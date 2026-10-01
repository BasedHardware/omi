/// Swiping a conversation row to delete (#20038): the row's card stays and a round red delete button
/// grows in at its edge; the full-width red block is gone. The confirm and Undo path is unchanged.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  late ConversationProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
  });
  tearDown(() => provider.dispose());

  Future<void> pumpRow(WidgetTester tester) async {
    final conversation = ServerConversation(
      id: 'a',
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Design review', 'Overview', emoji: '🧠'),
      status: ConversationStatus.completed,
    );
    provider.conversations = [conversation];
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: provider),
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: ConversationListItem(conversation: conversation, date: DateTime(2026, 9, 20), conversationIdx: 0),
        ),
      ),
    ));
  }

  double revealOpacity(WidgetTester tester) => tester
      .widget<Opacity>(find
          .ancestor(of: find.byKey(const ValueKey('conversation_swipe_delete')), matching: find.byType(Opacity))
          .first)
      .opacity;

  bool hasRedBlock(WidgetTester tester) => tester.widgetList<Container>(find.byType(Container)).any((c) =>
      c.color == OmiColors.danger ||
      (c.decoration is BoxDecoration &&
          (c.decoration! as BoxDecoration).color == OmiColors.danger &&
          (c.decoration! as BoxDecoration).shape != BoxShape.circle));

  testWidgets('the swipe reveals a round delete button that grows in, never a red row', (tester) async {
    await pumpRow(tester);
    final button = find.byKey(const ValueKey('conversation_swipe_delete'));
    expect(button, findsNothing, reason: 'nothing shows at rest');

    final gesture = await tester.startGesture(tester.getCenter(find.byType(ConversationListItem)));
    await gesture.moveBy(const Offset(-20, 0));
    await gesture.moveBy(const Offset(-60, 0));
    await tester.pump();
    final partway = revealOpacity(tester);
    expect(partway, greaterThan(0));
    expect(partway, lessThan(1));

    await gesture.moveBy(const Offset(-320, 0));
    await tester.pump();
    expect(revealOpacity(tester), 1);
    expect(tester.getSize(find.byKey(const ValueKey('conversation_swipe_delete'))), const Size(44, 44));
    expect(hasRedBlock(tester), isFalse, reason: 'only the round button is red');
    await gesture.up();
    await tester.pumpAndSettle();

    // Past the delete point: the confirm opens over the card with its small button, not a red row.
    expect(find.text('Delete Conversation?'), findsOneWidget);
    expect(hasRedBlock(tester), isFalse);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Delete Conversation?'), findsNothing);
    expect(button.evaluate().isEmpty || revealOpacity(tester) == 0, isTrue,
        reason: 'Cancel slides the row back and the button fades out');
  });
}
