import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/day_tasks_page.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart' show parseRecapDate;
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  // The journey preview builds proxy URLs from Env.apiBaseUrl (per-isolate statics).
  setUpAll(() => Env.init(_TestEnvFields()));

  testWidgets('renders journey locations as compact accessible map rows', (tester) async {
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(summaryId: 'summary-1', summary: _summary()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    final firstRow = find.byKey(const ValueKey('daily_summary_location_row_0'));
    final secondRow = find.byKey(const ValueKey('daily_summary_location_row_1'));
    final contentWidth = tester.getSize(find.byType(Scaffold)).width - 40;

    expect(firstRow, findsOneWidget);
    expect(secondRow, findsOneWidget);
    expect(tester.getSize(firstRow).width, contentWidth);
    expect(tester.getSize(firstRow).height, lessThan(60));
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Office'), findsOneWidget);

    final rowSemantics = tester.widget<Semantics>(find.ancestor(of: firstRow, matching: find.byType(Semantics)).first);
    expect(rowSemantics.properties.label, 'Home, 8AM');
    expect(rowSemantics.properties.button, isTrue);
    expect(rowSemantics.properties.onTap, isNotNull);
    semantics.dispose();
  });

  testWidgets('empty-address pins at distinct GPS points render as separate Unknown rows', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(
          summaryId: 'summary-empty-addr',
          summary: _summary(
            locations: [
              LocationPin(latitude: 37.7749, longitude: -122.4194, time: '08:00'),
              LocationPin(latitude: 37.7849, longitude: -122.4094, time: '10:00'),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(find.byKey(const ValueKey('daily_summary_location_row_0')), findsOneWidget);
    expect(find.byKey(const ValueKey('daily_summary_location_row_1')), findsOneWidget);
    expect(find.byKey(const ValueKey('daily_summary_location_row_2')), findsNothing);
    expect(find.text('Unknown'), findsNWidgets(2));
  });

  testWidgets('memories learned render as review rows above the prose learnings', (tester) async {
    final memoriesProvider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([
        Memory(
          id: 'mem-1',
          uid: 'summary-user',
          content: 'Prefers async standups',
          category: MemoryCategory.system,
          createdAt: DateTime.utc(2026, 7, 15),
          updatedAt: DateTime.utc(2026, 7, 15),
          visibility: MemoryVisibility.private,
        ),
      ], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(memoriesProvider.dispose);
    await memoriesProvider.loadMemories();

    await tester.pumpWidget(
      ChangeNotifierProvider<MemoriesProvider>.value(
        value: memoriesProvider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: ThemeData.dark(),
          home: DailySummaryDetailPage(
            summaryId: 'summary-learned',
            summary: _summary(
              locations: const [],
              memoriesLearned: const [
                MemoryReviewItem(memoryId: 'mem-1', content: 'Prefers async standups', category: 'work'),
              ],
              knowledgeNuggets: [KnowledgeNugget(insight: 'Async beats status meetings')],
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(find.byType(MemoryReviewCard), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_mem-1')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_reject_mem-1')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_fix_mem-1')), findsOneWidget);
    // The LLM-prose learnings are untouched, and stay below the review rows.
    expect(find.text('Async beats status meetings'), findsOneWidget);
    expect(
      tester.getTopLeft(find.byType(MemoryReviewCard)).dy,
      lessThan(tester.getTopLeft(find.text('Async beats status meetings')).dy),
    );
  });

  testWidgets('memories learned are tappable on a cold provider without the id loaded', (tester) async {
    final reviews = <String>[];
    final memoriesProvider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async {
        reviews.add(id);
        return true;
      },
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(memoriesProvider.dispose);
    // Cold start: nothing has initialised the provider and the bulk list never
    // contains the recap id.
    expect(memoriesProvider.loading, isTrue);

    await tester.pumpWidget(
      ChangeNotifierProvider<MemoriesProvider>.value(
        value: memoriesProvider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: ThemeData.dark(),
          home: DailySummaryDetailPage(
            summaryId: 'summary-cold',
            summary: _summary(
              locations: const [],
              memoriesLearned: const [
                MemoryReviewItem(memoryId: 'mem-cold', content: 'Prefers async standups', category: 'work'),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    final accept = tester.widget<InkWell>(find.byKey(const Key('memory_review_accept_mem-cold')));
    expect(accept.onTap, isNotNull);

    await tester.tap(find.byKey(const Key('memory_review_accept_mem-cold')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(reviews, ['mem-cold']);
  });

  testWidgets('the conversations stat opens the day page with the recap-day bounds', (tester) async {
    final bounds = <({DateTime start, DateTime end})>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(
          summaryId: 'summary-nav',
          summary: _summary(locations: const []),
          dayConversationsFetcher: ({required endDate, limit = 50, offset = 0, required startDate}) async {
            bounds.add((start: startDate, end: endDate));
            return (items: <ServerConversation>[], ok: true, truncated: false);
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    final stat = find.byKey(const ValueKey('recap_conversations_stat'));
    expect(stat, findsOneWidget);
    final semantics = tester.widget<Semantics>(stat);
    expect(semantics.properties.label, '1 conversation');

    await tester.tap(stat);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(find.byType(DayConversationsPage), findsOneWidget);
    expect(bounds, hasLength(1));
    expect(bounds.first.start, DateTime(2026, 7, 15));
    expect(bounds.first.end, DateTime(2026, 7, 16).subtract(const Duration(microseconds: 1)));
  });

  testWidgets('the tasks stat opens the day tasks page with the recap-day bounds', (tester) async {
    final bounds = <({DateTime start, DateTime end})>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(
          summaryId: 'summary-nav-tasks',
          summary: _summary(locations: const []),
          dayTasksFetcher: ({required endDate, limit = 50, offset = 0, required startDate}) async {
            bounds.add((start: startDate, end: endDate));
            return const ApiSuccess(ActionItemsResponse(actionItems: []));
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    final stat = find.byKey(const ValueKey('recap_tasks_stat'));
    expect(stat, findsOneWidget);
    final semantics = tester.widget<Semantics>(stat);
    expect(semantics.properties.label, '0 tasks');

    await tester.tap(stat);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(find.byType(DayTasksPage), findsOneWidget);
    expect(bounds, hasLength(1));
    expect(bounds.first.start, DateTime(2026, 7, 15));
    expect(bounds.first.end, DateTime(2026, 7, 16).subtract(const Duration(microseconds: 1)));
  });

  test('impossible recap dates never parse to a navigable day', () {
    expect(parseRecapDate('2026-02-30'), isNull);
    expect(parseRecapDate('2026-13-01'), isNull);
    expect(parseRecapDate('15-07-2026'), isNull);
    expect(parseRecapDate('2026-07-15'), DateTime(2026, 7, 15));
  });

  testWidgets('shows positive desktop watching and proactive stats', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(
          summaryId: 'summary-stats',
          summary: _summary(
            stats: DayStats(totalConversations: 1, totalDurationMinutes: 30, watchingMinutes: 17, proactiveMoments: 9),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('17m'), findsOneWidget);
    expect(find.text('9'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

DailySummary _summary({
  List<LocationPin>? locations,
  List<MemoryReviewItem> memoriesLearned = const [],
  List<KnowledgeNugget> knowledgeNuggets = const [],
  DayStats? stats,
}) {
  return DailySummary(
    id: 'summary-1',
    date: '2026-07-15',
    createdAt: DateTime(2026, 7, 16),
    headline: 'A day around the city',
    overview: 'A productive day.',
    stats: stats ?? DayStats(totalConversations: 1, totalDurationMinutes: 30),
    memoriesLearned: memoriesLearned,
    knowledgeNuggets: knowledgeNuggets,
    locations: locations ??
        [
          LocationPin(latitude: 37.7749, longitude: -122.4194, address: 'Home, San Francisco', time: '08:00'),
          LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '10:00'),
        ],
  );
}
