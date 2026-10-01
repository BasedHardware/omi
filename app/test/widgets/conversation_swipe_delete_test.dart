/// Swiping a conversation row to delete (#20038): the card swipes open to a round red delete button,
/// and the confirm is a small menu that pops from that button. The delete path is unchanged:
/// confirm unless opted out, then Undo.
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

  final card = find.byKey(const ValueKey('conversation_card'));
  final button = find.byKey(const ValueKey('conversation_swipe_delete'));
  final deleteItem = find.text('Delete Conversation');

  /// A finger's swipe: many small moves, as a real drag arrives.
  Future<void> swipe(WidgetTester tester, double dx) async {
    final gesture = await tester.startGesture(tester.getCenter(card));
    const steps = 12;
    for (var i = 0; i < steps; i++) {
      await gesture.moveBy(Offset(dx / steps, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
  }

  double buttonOpacity(WidgetTester tester) =>
      tester.widget<Opacity>(find.ancestor(of: button, matching: find.byType(Opacity)).first).opacity;

  testWidgets('a short swipe leaves the row open on the delete button; a tap on the card closes it', (tester) async {
    await pumpRow(tester);
    final rest = tester.getRect(card);
    expect(buttonOpacity(tester), 0, reason: 'nothing shows at rest');

    await swipe(tester, -100);
    final open = tester.getRect(card);
    expect(rest.left - open.left, 76, reason: 'open by the button and the air around it');
    expect(open.size, rest.size, reason: 'the card moves whole');
    expect(buttonOpacity(tester), 1);
    expect(open.right, lessThan(tester.getRect(button).left), reason: 'the button sits in the space the card left');
    expect(deleteItem, findsNothing, reason: 'a short swipe does not ask');

    await tester.tapAt(open.center);
    await tester.pumpAndSettle();
    expect(tester.getRect(card), rest);
  });

  testWidgets('a swipe the system cancels mid-drag still settles closed or open, never halfway', (tester) async {
    await pumpRow(tester);
    final rest = tester.getRect(card);
    for (final dx in [-20.0, -60.0, -200.0]) {
      final gesture = await tester.startGesture(tester.getCenter(card));
      for (var i = 0; i < 12; i++) {
        await gesture.moveBy(Offset(dx / 12, 0));
        await tester.pump(const Duration(milliseconds: 16));
      }
      await gesture.cancel();
      await tester.pumpAndSettle();
      final shift = rest.left - tester.getRect(card).left;
      expect(shift, anyOf(0, 76), reason: 'cancelled at $dx');
      expect(deleteItem, findsNothing, reason: 'short of 40% of the row it does not ask');
      if (shift > 0) {
        await tester.tapAt(tester.getRect(card).center);
        await tester.pumpAndSettle();
      }
    }
  });

  testWidgets('the delete button asks in a menu below it; tapping outside cancels and closes the row', (tester) async {
    await pumpRow(tester);
    final rest = tester.getRect(card);
    await swipe(tester, -100);

    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(deleteItem, findsOneWidget);
    expect(find.text('This also deletes its memories, tasks, and audio files.'), findsOneWidget);
    expect(find.text("Don't ask me again"), findsOneWidget);
    final item = tester.getRect(find.byKey(const ValueKey('omi_confirm_menu_confirm')));
    final anchor = tester.getRect(button);
    expect(item.top, greaterThan(anchor.bottom), reason: 'the menu opens below the button');
    expect(item.right, moreOrLessEquals(anchor.right), reason: 'and lines up with its trailing edge');

    await tester.tapAt(const Offset(10, 400));
    await tester.pumpAndSettle();
    expect(deleteItem, findsNothing);
    expect(tester.getRect(card), rest);
    expect(provider.conversations, hasLength(1));
  });

  testWidgets('a long swipe asks straight away; Delete Conversation deletes with Undo', (tester) async {
    await pumpRow(tester);
    await swipe(tester, -340);
    expect(deleteItem, findsOneWidget);

    await tester.tap(deleteItem);
    await tester.pumpAndSettle();
    expect(provider.conversations, isEmpty);
    expect(find.text('Undo'), findsOneWidget);

    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(provider.conversations, hasLength(1));
  });

  testWidgets('with "Don\'t ask me again" ticked, the next swipe deletes without asking', (tester) async {
    await pumpRow(tester);
    await swipe(tester, -340);
    expect(find.byIcon(Icons.check_rounded), findsNothing);
    await tester.tap(find.text("Don't ask me again"));
    await tester.pump();
    expect(find.byIcon(Icons.check_rounded), findsOneWidget);
    await tester.tap(deleteItem);
    await tester.pumpAndSettle();
    expect(SharedPreferencesUtil().showConversationDeleteConfirmation, isFalse);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();

    await swipe(tester, -340);
    expect(deleteItem, findsNothing);
    expect(provider.conversations, isEmpty);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
  });
}
