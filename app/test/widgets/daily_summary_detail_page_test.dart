import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

void main() {
  testWidgets('renders journey locations as compact accessible map rows', (tester) async {
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(summaryId: 'summary-1', summary: _summary(), tileProvider: _MemoryTileProvider()),
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
          tileProvider: _MemoryTileProvider(),
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
            tileProvider: _MemoryTileProvider(),
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
            tileProvider: _MemoryTileProvider(),
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
          tileProvider: _MemoryTileProvider(),
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

class _MemoryTileProvider extends TileProvider {
  static final _tile = MemoryImage(
    base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='),
  );

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) => _tile;
}
