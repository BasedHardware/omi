import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/synced_conversation_list_item.dart';
import 'package:omi/ui/ui.dart';

void main() {
  testWidgets('a screen reader opens the row and reaches Reprocess as its action', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SyncedConversationListItem(
            conversation: ServerConversation(
              id: 'c1',
              createdAt: DateTime(2026, 10, 1, 9),
              structured: Structured('Standup', ''),
            ),
            date: DateTime(2026, 10, 1),
            conversationIdx: 0,
            showReprocess: true,
          ),
        ),
      ),
    );
    final en = lookupAppLocalizations(const Locale('en'));

    // One node: a tap opens the conversation, and Reprocess is a named action on it.
    final data = tester.getSemantics(find.byType(OmiSettingsRow)).getSemanticsData();
    expect(data.hasAction(SemanticsAction.tap), isTrue);
    expect(
      [for (final id in data.customSemanticsActionIds ?? const <int>[]) CustomSemanticsAction.getAction(id)!.label],
      [en.reprocessConversation],
    );
    expect(find.bySemanticsLabel(en.reprocessConversation), findsNothing);
    handle.dispose();
  });
}
