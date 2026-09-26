import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Over the plan's minutes, a conversation is locked: the row keeps its title, time and length, and
/// its summary blurs under a small "Unlimited" badge — no dark box over the row, no label printed
/// over its text.
void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pump(WidgetTester tester, ServerConversation conversation) async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    )..conversations = [conversation];
    addTearDown(provider.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
      value: provider,
      child: MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: ConversationListItem(conversation: conversation, date: DateTime.utc(2026), conversationIdx: 0),
        ),
      ),
    ));
    await tester.pump();
  }

  ServerConversation pricing({required bool locked, String overview = 'Plus vs Unlimited and the annual discount.'}) =>
      ServerConversation(
        id: 'c1',
        createdAt: DateTime.utc(2026, 9, 25, 23, 52),
        startedAt: DateTime.utc(2026, 9, 25, 23, 52),
        finishedAt: DateTime.utc(2026, 9, 26, 0, 10),
        structured: Structured('Pricing review', overview),
        isLocked: locked,
      );

  testWidgets('a locked row keeps its title, blurs its summary and wears one small badge', (tester) async {
    final semantics = tester.ensureSemantics();
    await pump(tester, pricing(locked: true));
    expect(find.text('Pricing review'), findsOneWidget);
    expect(find.byKey(const Key('conversation_locked_badge')), findsOneWidget);
    expect(find.text(en.unlimitedBadge), findsOneWidget);
    expect(
      find.ancestor(of: find.text('Plus vs Unlimited and the annual discount.'), matching: find.byType(ImageFiltered)),
      findsOneWidget,
      reason: 'the summary is never readable',
    );
    expect(find.text(en.upgradeToUnlimited), findsNothing, reason: 'no label printed over the row');
    expect(find.bySemanticsLabel(RegExp(RegExp.escape(en.upgradeToUnlimited))), findsOneWidget,
        reason: 'screen readers hear why, as part of the row');
    expect(find.byIcon(Icons.chevron_right), findsNothing, reason: 'the badge is the affordance');
    semantics.dispose();
  });

  testWidgets('a locked row with no summary sent still shows the blurred shape, not an empty gap', (tester) async {
    await pump(tester, pricing(locked: true, overview: ''));
    expect(find.byKey(const Key('conversation_locked_badge')), findsOneWidget);
    expect(find.byType(ImageFiltered), findsOneWidget);
  });

  testWidgets('an unlocked row is untouched', (tester) async {
    await pump(tester, pricing(locked: false));
    expect(find.byKey(const Key('conversation_locked_badge')), findsNothing);
    expect(find.byType(ImageFiltered), findsNothing);
    expect(find.text('Plus vs Unlimited and the annual discount.'), findsOneWidget);
    expect(find.byIcon(Icons.chevron_right), findsOneWidget);
  });
}
