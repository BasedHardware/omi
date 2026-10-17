import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ServerConversation _conversation(String id, DateTime day, {int minute = 0}) => ServerConversation(
    id: id,
    createdAt: DateTime(day.year, day.month, day.day, 9, minute),
    startedAt: DateTime(day.year, day.month, day.day, 9, minute),
    structured: Structured('Talk $id', 'Overview'));

class _Fetch {
  final calls = <({DateTime start, int offset})>[];
  bool ok = true;
  bool truncated = false;
  List<ServerConversation> Function(DateTime start, int offset) rows = (_, __) => const [];

  Future<({List<ServerConversation> items, bool ok, bool truncated})> call(
      {required DateTime startDate, required DateTime endDate, int limit = 50, int offset = 0}) async {
    calls.add((start: startDate, offset: offset));
    return (items: ok ? rows(startDate, offset) : <ServerConversation>[], ok: ok, truncated: truncated);
  }
}

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
  final day = DateTime(2026, 9, 2);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<_Fetch> pumpDay(WidgetTester tester, {DateTime? date, void Function(_Fetch fetch)? configure}) async {
    NativeTestHost.install();
    final fetch = _Fetch();
    configure?.call(fetch);
    await tester.pumpWidget(NativeTestHost.app(MultiProvider(providers: [
      ChangeNotifierProvider<ConnectivityProvider>(create: (_) => _Connectivity()),
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
    ], child: Scaffold(body: DayConversationsPage(date: date ?? day, fetchConversations: fetch.call)))));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 300));
    return fetch;
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));

  List<NativeRow> rows(WidgetTester tester) =>
      IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface)));

  NativeRow row(WidgetTester tester, String id) => rows(tester).singleWhere((row) => row.id == id);

  String dayHeader(WidgetTester tester, DateTime date) =>
      OmiDateFormat.of(tester.element(find.byType(IosNativeSurface))).dayHeader(date);

  testWidgets('previous and next move a day; next stops at today', (tester) async {
    final fetch = await pumpDay(tester, configure: (fetch) => fetch.rows = (start, _) => [_conversation('a', start)]);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(surface(tester).title, dayHeader(tester, day));
    expect(surface(tester).toolbar.map((row) => row.id), ['day_back', 'day_previous', 'day_next', 'day_pick']);

    await row(tester, 'day_previous').action!(null);
    await tester.pump();
    expect(fetch.calls.last.start, DateTime(2026, 9, 1));
    expect(surface(tester).title, dayHeader(tester, DateTime(2026, 9, 1)));
    await row(tester, 'day_next').action!(null);
    await tester.pump();
    expect(fetch.calls.last.start, day);

    await tester.pumpWidget(const SizedBox());
    final now = DateTime.now();
    await pumpDay(tester, date: now);
    expect(row(tester, 'day_next').projection['enabled'], isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the calendar picks a day natively; cancel keeps it and a refusal opens the Flutter calendar',
      (tester) async {
    final fetch = await pumpDay(tester);
    final presented = _answerPresentations((snapshot) => {
          'action': 'apply',
          'values': {'day_pick_date': '${DateTime(2026, 8, 20, 15).millisecondsSinceEpoch}'},
        });
    await row(tester, 'day_pick').action!(null);
    await tester.pump();
    expect(presented.single['title'], _l10n.filterByDate);
    final pickRow = ((presented.single['sections'] as List).single as Map)['rows'].single as Map;
    expect(pickRow['kind'], 'date');
    expect(pickRow['value'], '${day.millisecondsSinceEpoch}');
    expect(fetch.calls.last.start, DateTime(2026, 8, 20));

    _answerPresentations((snapshot) => {'action': 'cancel', 'values': <String, Object?>{}});
    final calls = fetch.calls.length;
    await row(tester, 'day_pick').action!(null);
    await tester.pump();
    expect(fetch.calls, hasLength(calls));

    _answerPresentations((_) => null);
    unawaited(Future.sync(() => row(tester, 'day_pick').action!(null)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byKey(const Key('date_range_done')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the Show more row pages when it becomes visible', (tester) async {
    final fetch = await pumpDay(tester,
        configure: (fetch) => fetch.rows = (start, offset) => [
              for (var i = 0; i < (offset == 0 ? 50 : 3); i++) _conversation('c${offset + i}', start, minute: i % 60),
            ]);
    final more = row(tester, 'day_more');
    expect(more.onVisible, isNotNull);
    await more.onVisible!(null);
    await tester.pump();
    expect(fetch.calls.last.offset, 50);
    expect(rows(tester).where((row) => row.id.startsWith('day_conversation_')), hasLength(53));
    expect(rows(tester).where((row) => row.id == 'day_more'), isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a failed day shows the error, an empty day names it, and a partial day offers a retry', (tester) async {
    final failing = await pumpDay(tester, configure: (fetch) => fetch.ok = false);
    expect(surface(tester).failed, isTrue);
    expect(surface(tester).errorMessage, _l10n.somethingWentWrong);
    // Retry reloads the day.
    await surface(tester).onRefresh!(null);
    expect(failing.calls, hasLength(2));

    await tester.pumpWidget(const SizedBox());
    await pumpDay(tester);
    expect(surface(tester).failed, isFalse);
    expect(rows(tester).where((row) => row.id.startsWith('day_conversation_')), isEmpty);
    expect(surface(tester).empty,
        _l10n.noConversationsOnDate(OmiDateFormat.of(tester.element(find.byType(IosNativeSurface))).date(day)));

    await tester.pumpWidget(const SizedBox());
    final fetch = await pumpDay(tester, configure: (fetch) {
      fetch.truncated = true;
      fetch.rows = (start, _) => [_conversation('a', start)];
    });
    expect(row(tester, 'day_partial').title, _l10n.searchPartialFailure);
    final calls = fetch.calls.length;
    await row(tester, 'day_partial_retry').action!(null);
    await tester.pump();
    expect(fetch.calls, hasLength(calls + 1));
    expect(tester.takeException(), isNull);
  });

  testWidgets('rows offer the row menu without Select, and Delete asks first', (tester) async {
    await pumpDay(tester, configure: (fetch) => fetch.rows = (start, _) => [_conversation('a', start)]);
    final conversation = row(tester, 'day_conversation_a');
    expect(conversation.kind, 'navigation');
    expect(conversation.options.keys, ['open', 'star', 'move', 'share', 'delete']);
    expect(conversation.swipeTrailing, ['delete']);

    final presented = _answerPresentations((snapshot) => {'action': 'cancel', 'values': <String, Object?>{}});
    await conversation.action!('delete');
    await tester.pump();
    expect(presented.single['title'], _l10n.deleteConversationTitle);
    expect(rows(tester).where((row) => row.id == 'day_conversation_a'), hasLength(1));
    expect(tester.takeException(), isNull);
  });
}
