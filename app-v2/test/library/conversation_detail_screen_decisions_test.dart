import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_detail_screen.dart';
import 'package:nooto_v2/library/conversation_model.dart';

Map<String, dynamic> _conversation({
  required List<Map<String, dynamic>>? decisions,
  List<Map<String, dynamic>>? actionItems,
  String overview = 'A summary paragraph for the meeting.',
  bool includeDecisionsKey = true,
}) {
  final structured = <String, dynamic>{
    'title': 'Sample meeting',
    'overview': overview,
    'action_items':
        actionItems ??
        [
          {'description': 'Send the deck', 'completed': false},
          {'description': 'Schedule follow-up', 'completed': true},
          {'description': 'Email finance', 'completed': false},
        ],
  };
  if (includeDecisionsKey) {
    structured['decisions'] = decisions ?? const <Map<String, dynamic>>[];
  }
  return {
    'id': 'c1',
    'created_at': '2026-04-30T10:00:00Z',
    'transcript_segments': const <Map<String, dynamic>>[
      {'speaker': 'SPEAKER_0', 'text': 'hi', 'is_user': true},
    ],
    'apps_results': const <Map<String, dynamic>>[],
    'structured': structured,
  };
}

Map<String, dynamic> _decision({
  String id = 'd1',
  String statement = 'Adopt the new API',
  String? ownerName,
  String? dueAt,
  String status = 'open',
  List<String> openQuestions = const <String>[],
  List<int> relatedActionItemIds = const <int>[],
}) {
  return {
    'id': id,
    'statement': statement,
    if (ownerName != null) 'owner_name': ownerName,
    if (dueAt != null) 'due_at': dueAt,
    'status': status,
    'open_questions': openQuestions,
    'related_action_item_ids': relatedActionItemIds,
  };
}

Widget _harness(ConversationItem item, {bool reducedMotion = false}) {
  final app = MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: ConversationDetailScreen(item: item),
  );
  if (!reducedMotion) return app;
  return MediaQuery(data: const MediaQueryData(disableAnimations: true), child: app);
}

void main() {
  testWidgets('renders DECISIONS section between OVERVIEW and ACTION ITEMS when decisions non-empty', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [_decision(statement: 'Adopt the new API', ownerName: 'Sarah')],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.text('OVERVIEW'), findsOneWidget);
    expect(find.text('DECISIONS'), findsOneWidget);
    expect(find.text('ACTION ITEMS'), findsOneWidget);
    expect(find.byType(DecisionsSection), findsOneWidget);

    final overviewY = tester.getTopLeft(find.text('OVERVIEW')).dy;
    final decisionsY = tester.getTopLeft(find.text('DECISIONS')).dy;
    final actionItemsY = tester.getTopLeft(find.text('ACTION ITEMS')).dy;
    expect(overviewY, lessThan(decisionsY));
    expect(decisionsY, lessThan(actionItemsY));

    expect(find.text('Adopt the new API'), findsOneWidget);
  });

  testWidgets(
    'renders zero-state caption when decisions key is present but the array is empty (extraction ran, found nothing)',
    (tester) async {
      final item = ConversationItem.fromJson(_conversation(decisions: const []));
      expect(item.hasDecisionsField, isTrue);
      expect(item.decisions, isEmpty);

      await tester.pumpWidget(_harness(item));
      await tester.pumpAndSettle();

      expect(find.byType(DecisionsSection), findsOneWidget);
      expect(find.text('DECISIONS'), findsOneWidget);
      expect(find.text('No decisions extracted from this meeting'), findsOneWidget);
    },
  );

  testWidgets('renders no DECISIONS section when decisions key is absent from structured', (tester) async {
    final item = ConversationItem.fromJson(_conversation(decisions: null, includeDecisionsKey: false));
    expect(item.hasDecisionsField, isFalse);

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.byType(DecisionsSection), findsNothing);
    expect(find.text('DECISIONS'), findsNothing);
    expect(find.text('No decisions extracted from this meeting'), findsNothing);
  });

  testWidgets('owner+due caption hidden when both fields null', (tester) async {
    final item = ConversationItem.fromJson(_conversation(decisions: [_decision(statement: 'Skip the redesign')]));

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    // No "due ..." caption text under the statement.
    expect(find.textContaining('due '), findsNothing);
  });

  testWidgets('renders open-questions overflow pill when count > 3', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [
          _decision(statement: 'Choose a vendor', openQuestions: const ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    // First 3 visible, 4th and 5th collapsed into overflow pill.
    expect(find.text('Q1'), findsOneWidget);
    expect(find.text('Q2'), findsOneWidget);
    expect(find.text('Q3'), findsOneWidget);
    expect(find.text('Q4'), findsNothing);
    expect(find.text('Q5'), findsNothing);
    expect(find.text('+2 more'), findsOneWidget);
  });

  testWidgets('exactly 3 open questions: no overflow pill', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [
          _decision(statement: 'x', openQuestions: const ['Q1', 'Q2', 'Q3']),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.text('Q1'), findsOneWidget);
    expect(find.text('Q2'), findsOneWidget);
    expect(find.text('Q3'), findsOneWidget);
    expect(find.textContaining('more'), findsNothing);
  });

  testWidgets('"View N related actions" link visible only when relatedActionItemIds non-empty', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [_decision(statement: 'No relation', relatedActionItemIds: const [])],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.textContaining('related action'), findsNothing);
  });

  testWidgets('"View 1 related action" uses singular form when N=1', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [
          _decision(statement: 'Pick A', relatedActionItemIds: const [0]),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.text('View 1 related action'), findsOneWidget);
    expect(find.textContaining('related actions'), findsNothing);
  });

  testWidgets('"View N related actions" uses plural form when N>1', (tester) async {
    final item = ConversationItem.fromJson(
      _conversation(
        decisions: [
          _decision(statement: 'Pick A', relatedActionItemIds: const [0, 1, 2]),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    expect(find.text('View 3 related actions'), findsOneWidget);
  });

  testWidgets('tapping "View N related actions" scrolls ACTION ITEMS header into view', (tester) async {
    // Many action items so ACTION ITEMS starts below the fold even with a
    // short overview — the scroll has somewhere to go but the link itself
    // is on-screen at initial render so we can tap it.
    final manyActions = List<Map<String, dynamic>>.generate(
      40,
      (i) => {'description': 'Action $i', 'completed': false},
    );
    final item = ConversationItem.fromJson(
      _conversation(
        overview: 'Short overview.',
        actionItems: manyActions,
        decisions: [
          _decision(statement: 'Pick A', relatedActionItemIds: const [0, 2]),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item));
    await tester.pumpAndSettle();

    final tapTarget = find.text('View 2 related actions');
    expect(tapTarget, findsOneWidget);

    final headerBefore = tester.getTopLeft(find.text('ACTION ITEMS')).dy;

    await tester.tap(tapTarget);
    // Drive the scroll animation. Don't call pumpAndSettle — the
    // 1500ms highlight-clear timer is intentionally non-animated, and
    // pumpAndSettle would loop forever on it. pump() one frame for the
    // scroll-completion microtask, then drive the explicit highlight
    // duration so the clear-state setState runs.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300)); // scroll finishes
    await tester.pump(const Duration(milliseconds: 1600)); // clears highlight

    // After scroll, ACTION ITEMS header is visible (scrolled up toward the
    // top of the viewport, so its dy is smaller than before — or at the
    // top edge).
    expect(find.text('ACTION ITEMS'), findsOneWidget);
    final headerAfter = tester.getTopLeft(find.text('ACTION ITEMS')).dy;
    final viewportSize = tester.getSize(find.byType(ListView));
    expect(headerAfter, greaterThanOrEqualTo(0));
    expect(headerAfter, lessThan(viewportSize.height));
    expect(headerAfter, lessThanOrEqualTo(headerBefore), reason: 'header should move up (or stay) after ensureVisible');
  });

  testWidgets('reduced-motion path: scroll happens but tint state stays empty', (tester) async {
    final manyActions = List<Map<String, dynamic>>.generate(
      40,
      (i) => {'description': 'Action $i', 'completed': false},
    );
    final item = ConversationItem.fromJson(
      _conversation(
        overview: 'Short overview.',
        actionItems: manyActions,
        decisions: [
          _decision(statement: 'Pick A', relatedActionItemIds: const [0, 2]),
        ],
      ),
    );

    await tester.pumpWidget(_harness(item, reducedMotion: true));
    await tester.pumpAndSettle();

    await tester.tap(find.text('View 2 related actions'));
    await tester.pumpAndSettle();

    // Section is now visible (scroll fired).
    expect(find.text('ACTION ITEMS'), findsOneWidget);

    // Reduced motion: the action item row's AnimatedContainer must NOT have
    // a brand-tinted background. Find the AnimatedContainer that wraps
    // "Action 0" (one of the related ids) and assert color is transparent.
    final action0Container = find.ancestor(of: find.text('Action 0'), matching: find.byType(AnimatedContainer)).first;
    final container = tester.widget<AnimatedContainer>(action0Container);
    final decoration = container.decoration as BoxDecoration?;
    expect(decoration?.color, Colors.transparent, reason: 'reduced-motion should skip the brand-tint highlight');
  });
}
