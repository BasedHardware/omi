import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/cards/jira_stuck_issues_card.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

DateTime _ago(int days) => DateTime.now().subtract(Duration(days: days));

DateTime _inHours(int hours) => DateTime.now().add(Duration(hours: hours));

Map<String, dynamic> _jiraItem(
  String id,
  String desc, {
  required String externalId,
  DateTime? createdAt,
  DateTime? dueAt,
  bool completed = false,
}) => {
  'id': id,
  'description': desc,
  'completed': completed,
  if (createdAt != null) 'created_at': createdAt.toUtc().toIso8601String(),
  if (dueAt != null) 'due_at': dueAt.toUtc().toIso8601String(),
  'external_source': {'source': 'jira', 'external_id': externalId, 'url': 'https://x.atlassian.net/browse/$externalId'},
};

Map<String, dynamic> _transcriptItem(String id, String desc, {DateTime? createdAt}) => {
  'id': id,
  'description': desc,
  'completed': false,
  if (createdAt != null) 'created_at': createdAt.toUtc().toIso8601String(),
};

Future<ActionItemsProvider> _providerWith(List<Map<String, dynamic>> items) async {
  final mock = MockClient((req) async => http.Response(jsonEncode({'action_items': items, 'has_more': false}), 200));
  final p = ActionItemsProvider(client: _client(mock));
  await p.fetchAll();
  return p;
}

void main() {
  group('jiraStuckIssuesCardFor generator', () {
    test('returns null when provider not ready', () {
      // ActionItemsProvider that hasn't fetched yet — `ready` is false until
      // the first fetchAll completes (or fails).
      final mock = MockClient((req) async => http.Response('{}', 200));
      final p = ActionItemsProvider(client: _client(mock));
      expect(p.ready, isFalse);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNull);
    });

    test('emits when 3+ stuck (>3 days old) Jira items exist', () async {
      final p = await _providerWith([
        _jiraItem('1', 'old 1', externalId: 'A-1', createdAt: _ago(5)),
        _jiraItem('2', 'old 2', externalId: 'A-2', createdAt: _ago(7)),
        _jiraItem('3', 'old 3', externalId: 'A-3', createdAt: _ago(10)),
        _jiraItem('4', 'fresh', externalId: 'A-4', createdAt: _ago(1)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNotNull);
      expect(card!.totalStuck, 3);
      expect(card.stuckIssues.length, 3);
      expect(card.dueSoon, 0);
      // Oldest first (10d, 7d, 5d).
      expect(card.stuckIssues.map((i) => i.externalSource!.externalId).toList(), ['A-3', 'A-2', 'A-1']);
    });

    test('does NOT emit when only 2 stuck and no due-soon', () async {
      final p = await _providerWith([
        _jiraItem('1', 'old 1', externalId: 'A-1', createdAt: _ago(5)),
        _jiraItem('2', 'old 2', externalId: 'A-2', createdAt: _ago(7)),
        _jiraItem('3', 'fresh', externalId: 'A-3', createdAt: _ago(1)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNull);
    });

    test('emits when 1+ due-soon even without 3 stuck', () async {
      final p = await _providerWith([
        _jiraItem('1', 'urgent', externalId: 'A-1', dueAt: _inHours(6)),
        _jiraItem('2', 'fresh', externalId: 'A-2', createdAt: _ago(1)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNotNull);
      expect(card!.dueSoon, 1);
      expect(card.stuckIssues, isEmpty);
    });

    test('counts multiple due-soon items', () async {
      final p = await _providerWith([
        _jiraItem('1', 'urgent A', externalId: 'A-1', dueAt: _inHours(2)),
        _jiraItem('2', 'urgent B', externalId: 'A-2', dueAt: _inHours(20)),
        _jiraItem('3', 'far due', externalId: 'A-3', dueAt: _inHours(48)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNotNull);
      expect(card!.dueSoon, 2);
    });

    test('ignores transcript-derived (non-Jira) items', () async {
      final p = await _providerWith([
        _transcriptItem('1', 'transcript old 1', createdAt: _ago(5)),
        _transcriptItem('2', 'transcript old 2', createdAt: _ago(7)),
        _transcriptItem('3', 'transcript old 3', createdAt: _ago(10)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNull);
    });

    test('ignores completed Jira items', () async {
      final p = await _providerWith([
        _jiraItem('1', 'done 1', externalId: 'A-1', createdAt: _ago(10), completed: true),
        _jiraItem('2', 'done 2', externalId: 'A-2', createdAt: _ago(10), completed: true),
        _jiraItem('3', 'done 3', externalId: 'A-3', createdAt: _ago(10), completed: true),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNull);
    });

    test('caps display list at 3, but totalStuck reflects all', () async {
      final p = await _providerWith([
        _jiraItem('1', 'a', externalId: 'A-1', createdAt: _ago(5)),
        _jiraItem('2', 'b', externalId: 'A-2', createdAt: _ago(6)),
        _jiraItem('3', 'c', externalId: 'A-3', createdAt: _ago(7)),
        _jiraItem('4', 'd', externalId: 'A-4', createdAt: _ago(8)),
        _jiraItem('5', 'e', externalId: 'A-5', createdAt: _ago(9)),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNotNull);
      expect(card!.stuckIssues.length, 3);
      expect(card.totalStuck, 5);
    });

    test('skips items with neither createdAt nor dueAt', () async {
      final p = await _providerWith([
        _jiraItem('1', 'no timestamps a', externalId: 'A-1'),
        _jiraItem('2', 'no timestamps b', externalId: 'A-2'),
        _jiraItem('3', 'no timestamps c', externalId: 'A-3'),
      ]);

      final card = jiraStuckIssuesCardFor(p);

      expect(card, isNull);
    });

    test('id is derived from local date — same day produces same id', () async {
      final p = await _providerWith([
        _jiraItem('1', 'a', externalId: 'A-1', createdAt: _ago(5)),
        _jiraItem('2', 'b', externalId: 'A-2', createdAt: _ago(6)),
        _jiraItem('3', 'c', externalId: 'A-3', createdAt: _ago(7)),
      ]);

      final fixed = DateTime(2026, 5, 1, 9, 0);
      final cardA = jiraStuckIssuesCardFor(p, now: fixed);
      final cardB = jiraStuckIssuesCardFor(p, now: fixed.add(const Duration(hours: 4)));

      expect(cardA, isNotNull);
      expect(cardB, isNotNull);
      // Same day → same id → `_maybeEmit` will dedupe naturally.
      expect(cardA!.id, cardB!.id);
      expect(cardA.id, 'jira-stuck-2026-05-01');
    });
  });

  group('JiraStuckIssuesCard JSON roundtrip', () {
    test('preserves all fields including stuck issues', () {
      final original = JiraStuckIssuesCard(
        dateKey: '2026-05-01',
        stuckIssues: [
          ActionItem(
            id: '1',
            description: 'fix login',
            completed: false,
            createdAt: DateTime.parse('2026-04-25T10:00:00Z'),
            externalSource: const ExternalSource(source: 'jira', externalId: 'PROJ-1', url: 'https://x/PROJ-1'),
          ),
        ],
        totalStuck: 5,
        dueSoon: 2,
        generatedAt: DateTime.parse('2026-05-01T12:00:00Z'),
      );

      final round = JiraStuckIssuesCard.fromJson(original.toJson());

      expect(round.dateKey, '2026-05-01');
      expect(round.stuckIssues.length, 1);
      expect(round.stuckIssues.first.externalSource!.externalId, 'PROJ-1');
      expect(round.totalStuck, 5);
      expect(round.dueSoon, 2);
      expect(round.kind, CardKind.jiraStuckIssues);
      expect(round.id, 'jira-stuck-2026-05-01');
    });
  });

  group('JiraStuckIssuesCard render', () {
    Widget harness(JiraStuckIssuesCard card, {void Function(int)? onSwitch}) => MaterialApp(
      home: Provider<HomeNav>.value(
        value: HomeNav(switchToTab: onSwitch ?? (_) {}),
        child: Scaffold(
          body: SingleChildScrollView(child: Builder(builder: (ctx) => card.render(ctx))),
        ),
      ),
    );

    testWidgets('renders header, due-soon line, and issue rows', (tester) async {
      final card = JiraStuckIssuesCard(
        dateKey: '2026-05-01',
        stuckIssues: [
          ActionItem(
            id: '1',
            description: 'fix login bug',
            completed: false,
            createdAt: _ago(5),
            externalSource: const ExternalSource(source: 'jira', externalId: 'PROJ-1', url: 'https://x/PROJ-1'),
          ),
        ],
        totalStuck: 1,
        dueSoon: 2,
        generatedAt: DateTime.now(),
      );

      await tester.pumpWidget(harness(card));
      await tester.pumpAndSettle();

      expect(find.text('Jira issues need attention'), findsOneWidget);
      expect(find.text('2 due in the next 24h'), findsOneWidget);
      expect(find.text('PROJ-1'), findsOneWidget);
      expect(find.text('fix login bug'), findsOneWidget);
    });

    testWidgets('shows "+N more stuck" when totalStuck exceeds visible', (tester) async {
      final card = JiraStuckIssuesCard(
        dateKey: '2026-05-01',
        stuckIssues: [
          ActionItem(
            id: '1',
            description: 'a',
            completed: false,
            createdAt: _ago(5),
            externalSource: const ExternalSource(source: 'jira', externalId: 'A-1', url: 'https://x/A-1'),
          ),
        ],
        totalStuck: 5,
        dueSoon: 0,
        generatedAt: DateTime.now(),
      );

      await tester.pumpWidget(harness(card));
      await tester.pumpAndSettle();

      expect(find.text('+4 more stuck'), findsOneWidget);
    });

    testWidgets('tap on card body switches to Plan tab', (tester) async {
      int? switched;
      final card = JiraStuckIssuesCard(
        dateKey: '2026-05-01',
        stuckIssues: const [],
        totalStuck: 0,
        dueSoon: 1,
        generatedAt: DateTime.now(),
      );

      await tester.pumpWidget(harness(card, onSwitch: (i) => switched = i));
      await tester.pumpAndSettle();

      // Tap the header text to hit the outer InkWell. (Inner issue rows have
      // their own InkWell that opens Jira, so we tap the header instead.)
      await tester.tap(find.text('Jira issues need attention'));
      await tester.pumpAndSettle();

      expect(switched, HomeNav.planTabIndex);
    });
  });
}
