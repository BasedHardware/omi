import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

class _Source extends GlobalSearchSource {
  _Source({this.conversationRows = const [], this.taskRows = const [], this.memoryRows = const []});

  final List<ServerConversation> conversationRows;
  final List<ActionItemWithMetadata> taskRows;
  final List<MemorySearchHit> memoryRows;
  final searches = <({String query, DateTime? start, DateTime? end})>[];

  @override
  Future<ApiResult<SearchOverview>> overview() async => const ApiSuccess(SearchOverview(starred: 3, people: 2));

  @override
  Future<ConversationSearchResult> conversations(String query,
      {String? speakerId, DateTime? startDate, DateTime? endDate}) async {
    searches.add((query: query, start: startDate, end: endDate));
    return ConversationSearchResult(
        items: conversationRows, currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);
  }

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async => const ApiSuccess([]);

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async => ApiSuccess(taskRows);

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async => ApiSuccess(memoryRows);
}

Person _person(String id, String name, {bool pinned = false}) => Person(
    id: id,
    name: name,
    createdAt: DateTime(2026, 1, 1),
    updatedAt: DateTime(2026, 1, 1),
    confidence: 'unverified',
    pinned: pinned);

String _ms(DateTime date) => '${date.millisecondsSinceEpoch}';

/// Answers each native presentation with [reply]; null from [reply] means the host refused it.
List<Map> _answerPresentations(Map<String, Object?>? Function(Map snapshot) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    final answer = reply(snapshot);
    if (answer == null) throw PlatformException(code: 'invalid_native_presentation');
    return answer;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

void main() {
  late PeopleProvider people;
  late MemoriesProvider memories;
  late NativeTestHost host;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<void> pumpSearch(WidgetTester tester, _Source source, {String? initialQuery}) async {
    host = NativeTestHost.install();
    people = PeopleProvider(
        loadPeople: () async => PeopleListResponse(people: [
              _person('p-maya', 'Maya Chen', pinned: true),
              _person('p-cs', 'Cs'),
              _person('p-thanks', 'Thanks'),
              _person('p-because', 'Because'),
            ]));
    memories = MemoriesProvider(
        fetchMemoriesRequest: ({limit = 100, offset = 0, thisDeviceOnly = false}) async =>
            const GetMemoriesResult(<Memory>[], true));
    addTearDown(people.dispose);
    addTearDown(memories.dispose);
    await tester.pumpWidget(NativeTestHost.app(MultiProvider(providers: [
      ChangeNotifierProvider<PeopleProvider>.value(value: people),
      ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
    ], child: Scaffold(body: GlobalSearchPage(source: source, initialQuery: initialQuery)))));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 400));
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last);

  List<NativeRow> rows(WidgetTester tester) =>
      IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface).last));

  NativeRow row(WidgetTester tester, String id) => rows(tester).singleWhere((row) => row.id == id);

  // debugDispatchRows projects even after a fallback, so each state also proves the native view is shown.
  void expectNative() {
    expect(find.byType(UiKitView), findsOneWidget);
    expect(host.created, isNotEmpty);
  }

  Future<void> pickDates(WidgetTester tester) async {
    unawaited(Future.sync(() => row(tester, 'search_date').action!(null)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
  }

  testWidgets('Apply filters by the picked range, a reversed range is swapped, and the section clears it',
      (tester) async {
    final source = _Source();
    await pumpSearch(tester, source);
    expect(row(tester, 'search_starred').subtitle, '3');
    expect(row(tester, 'search_people').subtitle, '2');
    expect(row(tester, 'search_recaps').subtitle, '');

    final early = DateTime(2026, 9, 1, 9), late = DateTime(2026, 9, 5, 9);
    final presented = _answerPresentations((snapshot) => {
          'action': 'apply',
          // A two-day range in September.
          'values': {'search_date_start': _ms(late), 'search_date_end': _ms(late.add(const Duration(days: 1)))},
        });
    await pickDates(tester);
    final modal = presented.single;
    expect(modal['title'], _l10n.filterByDate);
    expect((modal['toolbar'] as List).map((row) => row['id']), ['cancel', 'apply']);
    final dateRows = ((modal['sections'] as List).single as Map)['rows'] as List;
    expect(dateRows.map((row) => row['title']), [_l10n.dateRangeStart, _l10n.dateRangeEnd]);
    expect(dateRows.map((row) => row['minimumDate']), everyElement(_ms(DateTime(2020))));
    expect(source.searches.last.start, DateTime(2026, 9, 5));
    expect(source.searches.last.end, DateTime(2026, 9, 6, 23, 59, 59, 999, 999));
    expect(row(tester, 'search_date_filter_label').title, contains('–'));
    expectNative();

    // A reversed reply is swapped before it filters.
    _answerPresentations((snapshot) => {
          'action': 'apply',
          'values': {'search_date_start': _ms(late), 'search_date_end': _ms(early)},
        });
    await pickDates(tester);
    expect(source.searches.last.start, DateTime(2026, 9, 1));
    expect(source.searches.last.end, DateTime(2026, 9, 5, 23, 59, 59, 999, 999));

    await row(tester, 'search_date_clear').action!(null);
    await tester.pump(const Duration(milliseconds: 400));
    expect(rows(tester).where((row) => row.id == 'search_date_filter_label'), isEmpty);
    expect(row(tester, 'search_starred'), isNotNull, reason: 'An empty query with no filter browses again');
    expect(tester.takeException(), isNull);
  });

  testWidgets('Remove Filter clears, Cancel keeps it, and a refused modal opens the Flutter calendar', (tester) async {
    final source = _Source();
    await pumpSearch(tester, source);
    _answerPresentations((snapshot) => {
          'action': 'apply',
          'values': {'search_date_start': _ms(DateTime(2026, 9, 1)), 'search_date_end': _ms(DateTime(2026, 9, 3))},
        });
    await pickDates(tester);
    expect(row(tester, 'search_date_filter_label'), isNotNull);
    expectNative();

    final cancelled = _answerPresentations((snapshot) => {'action': 'cancel', 'values': <String, Object?>{}});
    final searches = source.searches.length;
    await pickDates(tester);
    expect(source.searches, hasLength(searches));
    expect((cancelled.single['toolbar'] as List).map((row) => row['id']), ['cancel', 'apply', 'clear']);
    expect(row(tester, 'search_date_filter_label'), isNotNull);

    _answerPresentations((snapshot) => {
          'action': 'clear',
          'values': {
            'search_date_start': _ms(DateTime(2026, 9, 1)),
            'search_date_end': _ms(DateTime(2026, 9, 3)),
          }
        });
    await pickDates(tester);
    expect(rows(tester).where((row) => row.id == 'search_date_filter_label'), isEmpty);

    _answerPresentations((_) => null);
    await pickDates(tester);
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byKey(const Key('date_range_done')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a single picked day opens that day', (tester) async {
    await pumpSearch(tester, _Source());
    _answerPresentations((snapshot) => {
          'action': 'apply',
          'values': {
            'search_date_start': _ms(DateTime(2026, 9, 2, 8)),
            'search_date_end': _ms(DateTime(2026, 9, 2, 20))
          },
        });
    await pickDates(tester);
    await tester.pump(const Duration(milliseconds: 600));
    expect(tester.widget<DayConversationsPage>(find.byType(DayConversationsPage)).date, DateTime(2026, 9, 2, 8));
    // Let the day's page request settle against its deadline.
    await tester.pump(const Duration(seconds: 16));
    expect(tester.takeException(), isNull);
  });

  testWidgets('results carry snippets, task states and the searched memory query', (tester) async {
    final source = _Source(conversationRows: [
      ServerConversation(
          id: 'c1',
          createdAt: DateTime(2026, 9, 2, 10),
          structured: Structured('Standup', ''),
          matchSnippets: const [TranscriptMatchSnippet(text: 'ship the notes today')]),
      ServerConversation(
          id: 'c2',
          createdAt: DateTime(2026, 9, 2, 11),
          structured: Structured('Hidden', ''),
          isLocked: true,
          matchSnippets: const [TranscriptMatchSnippet(text: 'private words')]),
    ], taskRows: const [
      ActionItemWithMetadata(id: 't1', description: 'Send notes', completed: true),
      ActionItemWithMetadata(id: 't2', description: 'Book room', completed: false),
    ], memoryRows: const [
      MemorySearchHit(id: 'm1', content: 'Notes go to the wiki'),
    ]);
    await pumpSearch(tester, source, initialQuery: 'notes yesterday');
    expect(source.searches.last.query, 'notes');
    expect(row(tester, 'search_conversation_0').subtitle, endsWith(' · ship the notes today'));
    expect(row(tester, 'search_conversation_1').title, _l10n.conversations);
    expect(row(tester, 'search_conversation_1').subtitle, isNot(contains('private words')));
    expect(row(tester, 'search_task_0').symbol, 'checkmark.circle');
    expect(row(tester, 'search_task_1').symbol, 'circle');
    expect(row(tester, 'search_date_filter_label').title, isNotEmpty);
    expectNative();

    unawaited(Future.sync(() => row(tester, 'search_memory_0').action!(null)));
    // Memories open filtered by the searched words, without the date phrase.
    expect(memories.searchQuery, 'notes');
  });

  testWidgets('the People scope renders the shared rows natively without management chrome', (tester) async {
    await pumpSearch(tester, _Source());
    await row(tester, 'search_people').action!(null);
    await tester.pump(const Duration(milliseconds: 400));
    expect(surface(tester).title, _l10n.people);
    expect(surface(tester).searchPlaceholder, _l10n.peopleSearchPlaceholder);
    expectNative();
    final ids = rows(tester).map((row) => row.id).toList();
    expect(ids, containsAll(['person_p-maya', 'person_p-cs', 'people_filter']));
    expect(ids, isNot(contains('people_select')));
    expect(ids, isNot(contains('people_add')));
    expect(ids, isNot(contains('people_cleanup')));
    expect(ids, isNot(contains('voice_ask_to_tag')));
    final cs = row(tester, 'person_p-cs');
    expect(cs.options.keys, ['open', 'pin', 'why', 'delete']);
    expect(cs.swipeLeading, ['pin']);
    expect(cs.swipeTrailing, ['delete']);

    // The search field drives the people query.
    await surface(tester).search!('cs');
    await tester.pump();
    expect(rows(tester).where((row) => row.id.startsWith('person_')).map((row) => row.id), ['person_p-cs']);
    expectNative();

    await row(tester, 'search_close').action!(null);
    await tester.pump();
    expect(surface(tester).title, _l10n.search);
    expect(tester.takeException(), isNull);
  });
}
