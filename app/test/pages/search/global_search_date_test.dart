import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';

class _Capture {
  String? query;
  DateTime? start;
  DateTime? end;
  int calls = 0;
}

class _CapturingSource extends GlobalSearchSource {
  final conversationCapture = _Capture();
  int otherKindCalls = 0;
  int dateRecapCalls = 0;
  DateTime? recapRangeEnd;
  List<ServerConversation> rows = const [];

  @override
  Future<ApiResult<SearchOverview>> overview() async =>
      const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

  @override
  Future<ConversationSearchResult> conversations(String query,
      {String? speakerId, DateTime? startDate, DateTime? endDate}) async {
    conversationCapture
      ..query = query
      ..start = startDate
      ..end = endDate;
    conversationCapture.calls++;
    return ConversationSearchResult(
        items: rows, currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);
  }

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async {
    otherKindCalls++;
    return const ApiSuccess(<DailySummary>[]);
  }

  DateTime? recapDate;

  @override
  Future<ApiResult<List<DailySummary>>> recapsInRange(String query, DateTime start, DateTime end) async {
    dateRecapCalls++;
    recapDate = start;
    recapRangeEnd = end;
    return recaps(query);
  }

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async {
    otherKindCalls++;
    return const ApiSuccess(<ActionItemWithMetadata>[]);
  }

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async {
    otherKindCalls++;
    return const ApiSuccess(<MemorySearchHit>[]);
  }
}

ServerConversation _conversation(String id, String title, DateTime started) => ServerConversation.fromJson({
      'id': id,
      'created_at': started.toUtc().toIso8601String(),
      'started_at': started.toUtc().toIso8601String(),
      'finished_at': started.add(const Duration(minutes: 10)).toUtc().toIso8601String(),
      'structured': {'title': title, 'overview': '', 'emoji': '', 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
    });

Future<void> _pumpSearch(WidgetTester tester, GlobalSearchSource source, {String? initialQuery}) {
  return tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: GlobalSearchPage(initialQuery: initialQuery, source: source)),
    ),
  ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('"bluetooth sept 12" filters conversations and keeps the other result groups visible', (tester) async {
    final source = _CapturingSource()..rows = [_conversation('c1', 'Bluetooth Talk', DateTime(2026, 9, 12, 9))];
    await _pumpSearch(tester, source, initialQuery: 'bluetooth sept 12');
    await tester.pump();
    await tester.pumpAndSettle();

    final now = DateTime.now();
    final expectedStart = DateTime(now.year, 9, 12);
    final expectedEnd = DateTime(now.year, 9, 13).subtract(const Duration(microseconds: 1));
    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, expectedStart);
    expect(source.conversationCapture.end, expectedEnd);
    expect(source.otherKindCalls, 3, reason: 'date filtering must not hide recaps, tasks, or memories');
    expect(source.dateRecapCalls, 1, reason: 'the recap API is queried for the selected local day');
    expect(source.recapDate, expectedStart);
    expect(source.recapRangeEnd, expectedEnd, reason: 'recaps cover the whole selected range, not just its first day');
    expect(find.text('Bluetooth Talk'), findsOneWidget);
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsOneWidget);
  });

  testWidgets('"yesterday" sends an empty text query inside yesterday\'s bounds', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source, initialQuery: 'yesterday');
    await tester.pump();
    await tester.pumpAndSettle();

    final now = DateTime.now();
    final expectedStart = DateTime(now.year, now.month, now.day - 1);
    final expectedEnd = DateTime(now.year, now.month, now.day).subtract(const Duration(microseconds: 1));
    expect(source.conversationCapture.query, '');
    expect(source.conversationCapture.start, expectedStart);
    expect(source.conversationCapture.end, expectedEnd);
    expect(source.conversationCapture.calls, 1);
  });

  testWidgets('clearing the chip strips the phrase and reruns without a range', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source, initialQuery: 'bluetooth sept 12');
    await tester.pump();
    await tester.pumpAndSettle();
    expect(source.conversationCapture.start, isNotNull);

    await tester.tap(find.byKey(const ValueKey('global_search_date_filter')));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, isNull);
    expect(source.conversationCapture.end, isNull);
    expect(source.otherKindCalls, 6, reason: 'the date search and the cleared search both retain all result kinds');
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsNothing);
    expect(find.byKey(const ValueKey('global_search_field')), findsOneWidget);
    final field = tester.widget<TextField>(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)));
    expect(field.controller!.text, 'bluetooth');
  });

  testWidgets('typing a fresh query keeps the global four-kind search when no date parses', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source);
    await tester.pumpAndSettle();

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
        'bluetooth');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, isNull);
    expect(source.otherKindCalls, 3);
  });

  Future<void> pickRange(WidgetTester tester, DateTime start, DateTime end) async {
    await tester.tap(find.byKey(const ValueKey('global_search_calendar')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    tester.widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2)).onValueChanged?.call([start, end]);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('date_range_done')));
    await tester.pump();
    await tester.pumpAndSettle();
  }

  testWidgets('a picked range replaces the typed phrase and closes on the end day', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source, initialQuery: 'bluetooth yesterday');
    await tester.pump();
    await tester.pumpAndSettle();
    expect(source.conversationCapture.start, isNotNull);

    await pickRange(tester, DateTime(2026, 7, 1), DateTime(2026, 7, 3));

    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, DateTime(2026, 7, 1));
    expect(source.conversationCapture.end, DateTime(2026, 7, 4).subtract(const Duration(microseconds: 1)));
    expect(source.otherKindCalls, 6);
    final field = tester.widget<TextField>(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)));
    expect(field.controller!.text, 'bluetooth');
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsOneWidget);
  });

  testWidgets('clearing the field keeps the picked range and its chip', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();
    await tester.pumpAndSettle();

    await pickRange(tester, DateTime(2026, 7, 1), DateTime(2026, 7, 3));
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsOneWidget);

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)), '');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(source.conversationCapture.query, '');
    expect(source.conversationCapture.start, DateTime(2026, 7, 1));
    expect(source.conversationCapture.end, DateTime(2026, 7, 4).subtract(const Duration(microseconds: 1)));
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsOneWidget);
  });

  testWidgets('a typed date phrase supersedes the picked range; the chip removes the filter', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source);
    await tester.pumpAndSettle();

    await pickRange(tester, DateTime(2026, 7, 1), DateTime(2026, 7, 3));
    expect(source.conversationCapture.start, DateTime(2026, 7, 1));

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)),
        'bluetooth today');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    final now = DateTime.now();
    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, DateTime(now.year, now.month, now.day),
        reason: 'the newly parsed phrase wins over the picked range');
    expect(source.otherKindCalls, greaterThan(3), reason: 'date phrases retain the other result kinds');
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('global_search_date_filter')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(source.conversationCapture.query, 'bluetooth');
    expect(source.conversationCapture.start, isNull);
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsNothing);
  });

  testWidgets('a single picked day opens the day page instead of filtering', (tester) async {
    final source = _CapturingSource();
    await _pumpSearch(tester, source, initialQuery: 'bluetooth');
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('global_search_calendar')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    tester.widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2)).onValueChanged?.call([DateTime(2026, 7, 10)]);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('date_range_done')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(DayConversationsPage), findsOneWidget);
    expect(find.byKey(const ValueKey('global_search_date_filter')), findsNothing);
  });
}
