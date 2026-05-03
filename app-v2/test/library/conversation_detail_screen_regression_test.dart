import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_detail_screen.dart';
import 'package:nooto_v2/library/conversation_model.dart';

/// Builds a legacy / non-allowlisted conversation: NO `decisions` key on
/// `structured`. This is the shape every existing user sees today, and the
/// shape every non-allowlisted user will continue to see when the backend
/// ships the decisions extractor.
Map<String, dynamic> _legacyConversation() => {
  'id': 'conv-legacy',
  'created_at': '2026-04-30T10:00:00Z',
  'transcript_segments': [
    {'speaker': 'SPEAKER_0', 'text': 'Hello', 'is_user': true},
    {'speaker': 'SPEAKER_1', 'text': 'Hi there'},
  ],
  'apps_results': const <Map<String, dynamic>>[],
  'structured': {
    'title': 'Legacy meeting',
    'overview': 'A summary paragraph.',
    'action_items': [
      {'description': 'Send the deck', 'completed': false},
      {'description': 'Schedule follow-up', 'completed': true},
    ],
  },
};

Widget _harness(ConversationItem item) => MaterialApp(
  localizationsDelegates: const [
    AppLocalizations.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ],
  supportedLocales: AppLocalizations.supportedLocales,
  home: ConversationDetailScreen(item: item),
);

void main() {
  testWidgets(
    '[REGRESSION] non-allowlisted user (no decisions key) sees unchanged layout — overview, action items, transcript only',
    (tester) async {
      final item = ConversationItem.fromJson(_legacyConversation());
      // Sanity: the model still reports no decisions field.
      expect(item.hasDecisionsField, isFalse);
      expect(item.decisions, isEmpty);

      await tester.pumpWidget(_harness(item));
      await tester.pumpAndSettle();

      // No DecisionsSection widget anywhere in the tree.
      expect(find.byType(DecisionsSection), findsNothing);
      // No "DECISIONS" eyebrow text anywhere.
      expect(find.text('DECISIONS'), findsNothing);

      // Pre-existing sections still render.
      expect(find.text('OVERVIEW'), findsOneWidget);
      expect(find.text('ACTION ITEMS'), findsOneWidget);
      expect(find.text('TRANSCRIPT'), findsOneWidget);

      // Action item rows match the input — count and content.
      expect(find.text('Send the deck'), findsOneWidget);
      expect(find.text('Schedule follow-up'), findsOneWidget);

      // Transcript content rendered.
      expect(find.text('Hello'), findsOneWidget);
      expect(find.text('Hi there'), findsOneWidget);
    },
  );

  testWidgets('[REGRESSION] section order is OVERVIEW → ACTION ITEMS → TRANSCRIPT (top-to-bottom on screen)', (
    tester,
  ) async {
    final item = ConversationItem.fromJson(_legacyConversation());
    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    final overviewY = tester.getTopLeft(find.text('OVERVIEW')).dy;
    final actionItemsY = tester.getTopLeft(find.text('ACTION ITEMS')).dy;
    final transcriptY = tester.getTopLeft(find.text('TRANSCRIPT')).dy;

    expect(overviewY, lessThan(actionItemsY), reason: 'OVERVIEW must precede ACTION ITEMS');
    expect(actionItemsY, lessThan(transcriptY), reason: 'ACTION ITEMS must precede TRANSCRIPT');
  });
}
