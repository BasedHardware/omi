import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/action_items/day_tasks_page.dart';
import 'package:omi/pages/conversations/conversation_map_page.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart' show OmiSpinner;
import 'package:omi/widgets/components/memory_review_card.dart';
import 'package:omi/widgets/native_static_map.dart';
import 'package:omi/widgets/omi_map_preview.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'https://api.example.test/';
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

/// A static-map resolver whose fetches the test completes. Each fetch's file is a real temporary file.
class _Maps {
  _Maps(this.directory);

  final Directory directory;
  final requests = <({List<OmiMapPin> pins, int width, int height, Brightness brightness, bool Function() current})>[];
  final _pending = <Completer<String?>>[];
  var _count = 0;

  Future<String?> resolve({
    required List<OmiMapPin> pins,
    required int width,
    required int height,
    required Brightness brightness,
    required bool Function() current,
  }) {
    requests.add((pins: pins, width: width, height: height, brightness: brightness, current: current));
    final completer = Completer<String?>();
    _pending.add(completer);
    return completer.future;
  }

  /// Writes a map file and answers the fetch [index] with it; null answers a failed fetch.
  File? complete(int index, {bool fail = false}) {
    if (fail) {
      _pending[index].complete(null);
      return null;
    }
    final file = File('${directory.path}/omi_native_map_test_${_count++}.png')..writeAsBytesSync([137, 80, 78, 71]);
    _pending[index].complete(Uri.file(file.path).toString());
    return file;
  }
}

/// Lets real file I/O and the fake-async continuations between its steps finish.
Future<void> _settleIo(WidgetTester tester) async {
  for (var round = 0; round < 20; round++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 10)));
    await tester.pump();
  }
}

Map _snapshot(WidgetTester tester) => tester.widget<UiKitView>(find.byType(UiKitView).last).creationParams as Map;

List<NativeRow> _rows(WidgetTester tester) =>
    IosNativeSurface.debugDispatchRows(tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface)).last);

NativeRow? _row(WidgetTester tester, String id) => _rows(tester).where((row) => row.id == id).firstOrNull;

/// Sends a command whose action awaits a route, sheet or fetch the test resolves later.
Future<void> _tap(WidgetTester tester, NativeTestHost host, String id) async {
  unawaited(host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': null})));
  await tester.pump();
}

Future<Object?> _send(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  await tester.pump();
  return const StandardMethodCodec().decodeEnvelope(reply!);
}

ServerConversation _conversation(String id, double latitude, double longitude, {bool locked = false}) =>
    ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 8, 1, 9),
      structured: Structured('Title $id', 'Overview'),
      isLocked: locked,
      geolocation: Geolocation(latitude: latitude, longitude: longitude),
    );

/// a and b share a place; c and the locked d each have their own.
final _places = [
  _conversation('a', 37.77491, -122.41941),
  _conversation('b', 37.77494, -122.41944),
  _conversation('c', 40.7128, -74.0060),
  _conversation('d', 51.5074, -0.1278, locked: true),
];

DailySummary _summary({
  String date = '2026-07-15',
  DayStats? stats,
  List<MemoryReviewItem> memoriesLearned = const [],
  List<LocationPin>? locations,
}) =>
    DailySummary(
      id: 'summary-1',
      date: date,
      createdAt: DateTime(2026, 7, 16),
      headline: 'A day around the city',
      overview: 'A productive day.',
      stats: stats ?? DayStats(totalConversations: 1, totalDurationMinutes: 30),
      highlights: [
        TopicHighlight(topic: 'Planning', emoji: '🗓', summary: 'Planned the week', conversationIds: const ['conv-1']),
      ],
      memoriesLearned: memoriesLearned,
      locations: locations ??
          [
            LocationPin(latitude: 37.7749, longitude: -122.4194, address: 'Home, San Francisco', time: '08:00'),
            LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '10:00'),
            LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '13:30'),
          ],
    );

/// The config channel: activities stay up until Dart asks to dismiss them, which Swift confirms.
List<MethodCall> _installPresenter() {
  final calls = <MethodCall>[];
  final open = <int, Completer<Object?>>{};
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    calls.add(call);
    switch (call.method) {
      case 'presentActivity':
        final completer = Completer<Object?>();
        open[(call.arguments as Map)['requestId'] as int] = completer;
        return completer.future;
      case 'dismissPresentation':
        open.remove(call.arguments as int)?.complete({'values': <String, Object?>{}, 'reason': 'programmatic'});
    }
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return calls;
}

int _count(List<MethodCall> calls, String method) => calls.where((call) => call.method == method).length;

void main() {
  setUpAll(() => Env.init(_TestEnvFields()));

  late Directory directory;
  setUp(() => directory = Directory.systemTemp.createTempSync('omi_native_maps_recap_test'));
  tearDown(() => directory.deleteSync(recursive: true));

  group('conversation map', () {
    testWidgets('projects the map, Open in Maps and single and multi groups with locked titles', (tester) async {
      final host = NativeTestHost.install();
      final maps = _Maps(directory);
      final launched = <(double, double)>[];
      await tester.pumpWidget(NativeTestHost.app(ConversationMapPage(
        conversations: _places,
        launchMap: (latitude, longitude) => launched.add((latitude, longitude)),
        staticMapResolver: maps.resolve,
      )));
      await NativeTestHost.settle(tester);

      final groups = buildConversationMapGroups(_places);
      expect(groups.map((group) => group.conversations.length), [2, 1, 1]);
      expect(find.byType(UiKitView), findsOneWidget);
      final snapshot = _snapshot(tester);
      expect(snapshot['title'], 'Conversation Map');
      expect((snapshot['toolbar'] as List).map((row) => row['id']), ['conversation_map_back']);

      // The pins are exactly the classic preview's pins.
      final expected = normalizeOmiMapPins([
        for (final group in groups) OmiMapPin(latitude: group.latitude, longitude: group.longitude),
      ]);
      expect(maps.requests, hasLength(1));
      expect(maps.requests.single.pins.map((pin) => (pin.latitude, pin.longitude)),
          expected.map((pin) => (pin.latitude, pin.longitude)));
      expect(maps.requests.single.height, 220);

      // While the map loads there is no image and no error yet.
      expect(_row(tester, 'conversation_map_image'), isNull);
      expect(_row(tester, 'conversation_map_error'), isNull);
      expect(_row(tester, 'conversation_map_loading')!.title, 'Loading…');
      final file = maps.complete(0)!;
      await tester.pump();
      await tester.pump();
      final image = _row(tester, 'conversation_map_image')!;
      expect((image.kind, image.imageUri, image.maximumValue, image.valid),
          ('image', Uri.file(file.path).toString(), 4.0, true));

      final open = _row(tester, 'conversation_map_open')!;
      expect((open.title, open.symbol), ('Open in Maps', 'map'));
      expect(await _send(tester, host, 'conversation_map_open'), isNull);
      expect(launched, [(groups.first.latitude, groups.first.longitude)]);

      final rows = [for (var index = 0; index < 3; index++) _row(tester, 'conversation_map_group_$index')!];
      expect(rows.map((row) => (row.title, row.kind, row.symbol)), [
        ('2 conversations', 'navigation', 'square.stack'),
        ('Title c', 'navigation', 'mappin.circle.fill'),
        // Locked content never crosses the bridge.
        ('Conversations', 'navigation', 'mappin.circle.fill'),
      ]);
      expect(rows.every((row) => row.valid), isTrue);
      expect(_row(tester, 'conversation_map_group_3'), isNull);
    });

    testWidgets('a failed map shows Could not load map and keeps Open in Maps', (tester) async {
      NativeTestHost.install();
      final maps = _Maps(directory);
      await tester.pumpWidget(NativeTestHost.app(ConversationMapPage(
        conversations: _places,
        launchMap: (_, __) {},
        staticMapResolver: maps.resolve,
      )));
      await NativeTestHost.settle(tester);
      maps.complete(0, fail: true);
      await tester.pump();
      await tester.pump();
      expect(_row(tester, 'conversation_map_image'), isNull);
      expect(_row(tester, 'conversation_map_error')!.title, 'Could not load map');
      expect(_row(tester, 'conversation_map_open'), isNotNull);
    });

    testWidgets('empty states choose No conversations yet or Unknown location', (tester) async {
      NativeTestHost.install();
      final maps = _Maps(directory);
      for (final (conversations, empty) in [
        (<ServerConversation>[], 'No conversations yet'),
        (
          [ServerConversation(id: 'x', createdAt: DateTime.utc(2026), structured: Structured('X', ''))],
          'Unknown location'
        ),
      ]) {
        await tester.pumpWidget(NativeTestHost.app(
            ConversationMapPage(key: UniqueKey(), conversations: conversations, staticMapResolver: maps.resolve)));
        await NativeTestHost.settle(tester);
        final snapshot = _snapshot(tester);
        expect(snapshot['empty'], empty);
        expect(snapshot['sections'], isEmpty);
      }
      expect(maps.requests, isEmpty, reason: 'No pins, no map fetch');
    });

    testWidgets('the map file is deleted on dispose', (tester) async {
      NativeTestHost.install();
      final maps = _Maps(directory);
      await tester
          .pumpWidget(NativeTestHost.app(ConversationMapPage(conversations: _places, staticMapResolver: maps.resolve)));
      await NativeTestHost.settle(tester);
      final file = maps.complete(0)!;
      await tester.pump();
      await tester.pump();
      expect(file.existsSync(), isTrue);
      await tester.pumpWidget(const SizedBox());
      await _settleIo(tester);
      expect(file.existsSync(), isFalse);
    });

    testWidgets('a session change deletes the map file and withdraws the image', (tester) async {
      NativeTestHost.install();
      final maps = _Maps(directory);
      await tester
          .pumpWidget(NativeTestHost.app(ConversationMapPage(conversations: _places, staticMapResolver: maps.resolve)));
      await NativeTestHost.settle(tester);
      final file = maps.complete(0)!;
      await tester.pump();
      await tester.pump();
      expect(_row(tester, 'conversation_map_image'), isNotNull);
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pump();
      await _settleIo(tester);
      expect(file.existsSync(), isFalse);
      expect(find.byType(UiKitView), findsNothing, reason: 'The previous owner\'s surface shows nothing');
      expect(maps.requests, hasLength(1), reason: 'Nothing is fetched for the previous owner again');
    });

    testWidgets('a fetch completing after dispose is discarded and its file deleted', (tester) async {
      NativeTestHost.install();
      final maps = _Maps(directory);
      await tester
          .pumpWidget(NativeTestHost.app(ConversationMapPage(conversations: _places, staticMapResolver: maps.resolve)));
      await NativeTestHost.settle(tester);
      await tester.pumpWidget(const SizedBox());
      expect(maps.requests.single.current(), isFalse);
      final late = maps.complete(0)!;
      await tester.pump();
      await tester.pump();
      await _settleIo(tester);
      expect(late.existsSync(), isFalse);
    });

    testWidgets('a shared place opens its chooser sheet from the page', (tester) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(
          NativeTestHost.app(ConversationMapPage(conversations: _places, staticMapResolver: _Maps(directory).resolve)));
      await NativeTestHost.settle(tester);
      await _tap(tester, host, 'conversation_map_group_0');
      await tester.pump(const Duration(seconds: 1));
      // The compile-time flag is off in tests, so showOmiSheet keeps the classic chooser rows.
      expect(find.byKey(const ValueKey('conversation_map_cluster_row_a')), findsOneWidget);
      expect(find.byKey(const ValueKey('conversation_map_cluster_row_b')), findsOneWidget);
    });

    testWidgets('the cluster chooser projects rows, pops, then opens the chosen conversation', (tester) async {
      final host = NativeTestHost.install();
      final opened = <String>[];
      final conversations = [_places[0], _places[1], _places[3]];
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => ConversationMapClusterChooser(
                      title: '3 conversations',
                      conversations: conversations,
                      onOpen: (conversation) => opened.add(conversation.id),
                      fallback: const Text('classic chooser')))),
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);

      final rows = [for (var index = 0; index < 3; index++) _row(tester, 'conversation_map_cluster_$index')!];
      expect(rows.map((row) => row.title), ['Title a', 'Title b', 'Conversations']);
      expect(rows.every((row) => row.subtitle.isNotEmpty && row.kind == 'navigation' && row.valid), isTrue);
      expect(_row(tester, 'conversation_map_cluster_close'), isNotNull);

      final row = _row(tester, 'conversation_map_cluster_1')!;
      expect(await _send(tester, host, 'conversation_map_cluster_1'), isNull);
      // A second command before the sheet closes neither pops the page beneath nor opens twice.
      await row.action!(null);
      await tester.pumpAndSettle();
      expect(opened, ['b']);
      expect(find.text('open'), findsOneWidget);
      expect(find.byType(ConversationMapClusterChooser), findsNothing);
    });

    testWidgets('the cluster chooser opens nothing for another account session', (tester) async {
      NativeTestHost.install();
      final opened = <String>[];
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => ConversationMapClusterChooser(
                      title: '2 conversations',
                      conversations: [_places[0], _places[1]],
                      onOpen: (conversation) => opened.add(conversation.id),
                      fallback: const Text('classic chooser')))),
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      final row = _row(tester, 'conversation_map_cluster_0')!;
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pump();
      await row.action!(null);
      await tester.pumpAndSettle();
      expect(opened, isEmpty);
    });
  });

  group('recap', () {
    Widget page(DailySummary? summary,
            {Future<ServerConversation?> Function(String)? fetcher,
            Future<DailySummary?> Function(String)? loader,
            DayConversationsFetcher? dayConversations,
            DayTasksFetcher? dayTasks,
            void Function(double, double)? launch}) =>
        NativeTestHost.app(DailySummaryDetailPage(
          summaryId: 'summary-1',
          summary: summary,
          summaryLoader: loader,
          conversationFetcher: fetcher,
          dayConversationsFetcher: dayConversations,
          dayTasksFetcher: dayTasks,
          launchMap: launch,
        ));

    testWidgets('loading and not-found states are projected with Back and Go Back', (tester) async {
      NativeTestHost.install();
      final load = Completer<DailySummary?>();
      await tester.pumpWidget(page(null, loader: (_) => load.future));
      await NativeTestHost.settle(tester);
      var snapshot = _snapshot(tester);
      expect(snapshot['loading'], true);
      expect(snapshot['sections'], isEmpty);
      expect(_row(tester, 'recap_back'), isNotNull);

      load.complete(null);
      await NativeTestHost.settle(tester);
      snapshot = _snapshot(tester);
      expect(snapshot['loading'], false);
      expect(_row(tester, 'recap_not_found_label')!.title, 'Summary not found');
      expect(_row(tester, 'recap_go_back')!.title, 'Go Back');
    });

    testWidgets('the journey sheet projects the map, Open in Maps and 12-hour stops that launch', (tester) async {
      final host = NativeTestHost.install();
      final maps = _Maps(directory);
      final launched = <(double, double)>[];
      final summary = _summary();
      await tester.pumpWidget(NativeTestHost.app(Material(
          child: RecapJourneySheet(
              locations: summary.locations,
              onLaunch: (latitude, longitude) => launched.add((latitude, longitude)),
              staticMapResolver: maps.resolve,
              fallback: const Text('classic journey')))));
      await NativeTestHost.settle(tester);

      expect(_snapshot(tester)['title'], "Your Day's Journey");
      expect(maps.requests.single.height, 200);
      final file = maps.complete(0)!;
      await tester.pump();
      await tester.pump();
      expect(_row(tester, 'recap_journey_image')!.imageUri, Uri.file(file.path).toString());

      // Consecutive stops at one place merge into one time range, as in the classic timeline.
      final stops = [_row(tester, 'recap_location_0')!, _row(tester, 'recap_location_1')!];
      expect(stops.map((row) => (row.title, row.subtitle, row.symbol)),
          [('Home', '8AM', 'mappin'), ('Office', '10AM - 1:30PM', 'mappin')]);
      expect(_row(tester, 'recap_location_2'), isNull);

      expect(await _send(tester, host, 'recap_open_maps'), isNull);
      expect(await _send(tester, host, 'recap_location_1'), isNull);
      expect(launched, [(37.7749, -122.4194), (37.7849, -122.4094)]);

      await tester.pumpWidget(const SizedBox());
      await _settleIo(tester);
      expect(file.existsSync(), isFalse, reason: 'Closing the sheet deletes its map file');
    });

    testWidgets('the journey row opens the journey sheet', (tester) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(page(_summary()));
      await NativeTestHost.settle(tester);
      await _tap(tester, host, 'recap_locations_map');
      await tester.pump(const Duration(seconds: 1));
      // The compile-time flag is off in tests, so showOmiSheet keeps the classic journey builder.
      expect(find.byKey(const ValueKey('daily_summary_location_row_0')), findsOneWidget);
    });

    for (final outcome in ['success', 'error', 'unmount']) {
      testWidgets('the activity is dismissed exactly once on $outcome', (tester) async {
        final host = NativeTestHost.install();
        final calls = _installPresenter();
        final fetch = Completer<ServerConversation?>();
        await tester.pumpWidget(page(_summary(), fetcher: (_) => fetch.future));
        await NativeTestHost.settle(tester);
        await _tap(tester, host, 'recap_highlight_0');
        await tester.pump();
        expect(_count(calls, 'presentActivity'), 1);
        expect(find.byType(Dialog), findsNothing, reason: 'No Flutter spinner under the native activity');
        switch (outcome) {
          case 'success':
            fetch.complete(null);
          case 'error':
            fetch.completeError(StateError('offline'));
          case 'unmount':
            await tester.pumpWidget(const SizedBox());
            await tester.pump(const Duration(milliseconds: 600));
            fetch.complete(null);
        }
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 600));
        expect(_count(calls, 'dismissPresentation'), 1);
        if (outcome == 'error') expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);
        await tester.pump(const Duration(seconds: 10));
      });
    }

    testWidgets('without native presentation the Flutter spinner shows and is dismissed once', (tester) async {
      final fetch = Completer<ServerConversation?>();
      await tester.pumpWidget(page(_summary(), fetcher: (_) => fetch.future));
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(find.text('Planning'));
      await tester.pump();
      expect(find.byType(Dialog), findsNothing);
      expect(find.byType(OmiSpinner), findsOneWidget);
      fetch.complete(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(OmiSpinner), findsNothing);
      expect(find.byType(DailySummaryDetailPage), findsOneWidget, reason: 'Only the spinner was popped');
    });

    testWidgets('the memories row opens the review sheet', (tester) async {
      final host = NativeTestHost.install();
      final memories = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            const GetMemoriesResult([], true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: true),
        reviewMemoryRequest: (id, value) async => true,
        editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
      );
      addTearDown(memories.dispose);
      await tester.pumpWidget(ChangeNotifierProvider<MemoriesProvider>.value(
          value: memories,
          child: page(_summary(memoriesLearned: const [
            MemoryReviewItem(memoryId: 'mem-1', content: 'Prefers async standups', category: 'work'),
          ]))));
      await NativeTestHost.settle(tester);
      expect(find.byType(MemoryReviewCard), findsNothing);
      await _tap(tester, host, 'recap_review_memories');
      await tester.pumpAndSettle();
      final card = tester.widget<MemoryReviewCard>(find.byType(MemoryReviewCard));
      expect((card.source, card.impressionKey, card.title),
          (MemoryReviewSource.dailySummaryDetail, 'summary-1', 'Memories'));
      expect(card.items.single.memoryId, 'mem-1');
    });

    testWidgets('the stat rows match the classic tiles and route to the day pages', (tester) async {
      final host = NativeTestHost.install();
      final conversations = <DateTime>[];
      final tasks = <DateTime>[];
      await tester.pumpWidget(page(
        _summary(
            stats: DayStats(totalConversations: 1, totalDurationMinutes: 30, watchingMinutes: 17, proactiveMoments: 9)),
        dayConversations: ({required endDate, limit = 50, offset = 0, required startDate}) async {
          conversations.add(startDate);
          return (items: <ServerConversation>[], ok: true, truncated: false);
        },
        dayTasks: ({required endDate, limit = 50, offset = 0, required startDate}) async {
          tasks.add(startDate);
          return const ApiSuccess(ActionItemsResponse(actionItems: []));
        },
      ));
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'recap_stats'), isNull);
      expect([
        for (final id in [
          'recap_conversations_stat',
          'recap_duration_stat',
          'recap_tasks_stat',
          'recap_watching_stat',
          'recap_proactive_stat'
        ])
          (_row(tester, id)!.title, _row(tester, id)!.kind)
      ], [
        ('1 conversation', 'navigation'),
        ('30m', 'label'),
        ('0 tasks', 'navigation'),
        ('17m', 'label'),
        ('9', 'label'),
      ]);

      await _tap(tester, host, 'recap_conversations_stat');
      await tester.pumpAndSettle();
      expect(find.byType(DayConversationsPage), findsOneWidget);
      expect(conversations, [DateTime(2026, 7, 15)]);
      Navigator.of(tester.element(find.byType(DayConversationsPage))).pop();
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);

      await _tap(tester, host, 'recap_tasks_stat');
      await tester.pumpAndSettle();
      expect(find.byType(DayTasksPage), findsOneWidget);
      expect(tasks, [DateTime(2026, 7, 15)]);
    });

    testWidgets('stats stay labels without a parseable day, and zero extras are omitted', (tester) async {
      NativeTestHost.install();
      await tester.pumpWidget(page(_summary(date: '2026-02-30')));
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'recap_conversations_stat')!.kind, 'label');
      expect(_row(tester, 'recap_tasks_stat')!.kind, 'label');
      expect(_row(tester, 'recap_watching_stat'), isNull);
      expect(_row(tester, 'recap_proactive_stat'), isNull);
    });
  });

  group('resolveNativeStaticMapFile', () {
    // A 1x1 PNG.
    final png = Uint8List.fromList([
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, //
      0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
      0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0xF8, 0xCF, 0xC0, 0xF0,
      0x1F, 0x00, 0x05, 0x00, 0x01, 0xFF, 0x89, 0x99, 0x3D, 0x1D, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
      0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
    ]);
    const pins = [OmiMapPin(latitude: 37.77491, longitude: -122.41941)];

    Future<String?> resolve({bool Function()? current, String? header = 'Bearer token', List<OmiMapPin> pins = pins}) {
      final requested = <(String, Map<String, String>)>[];
      return resolveNativeStaticMapFile(
        pins: pins,
        width: 320,
        height: 200,
        brightness: Brightness.dark,
        current: current ?? () => true,
        authHeaderProvider: () async => header,
        imageProvider: (url, headers) {
          requested.add((url, headers));
          expect(url, buildOmiStaticMapUrl(pins: pins, width: 320, height: 200, brightness: Brightness.dark));
          expect(headers, {'Authorization': 'Bearer token'});
          return MemoryImage(png);
        },
        directory: () async => directory,
      );
    }

    testWidgets('writes the proxy image as a temporary PNG with the app header', (tester) async {
      final uri = await tester.runAsync(() => resolve());
      expect(uri, isNotNull);
      final file = File(Uri.parse(uri!).toFilePath());
      expect(file.uri.pathSegments.last, matches(RegExp(r'^omi_native_map_\d+\.png$')));
      expect(file.readAsBytesSync().take(4), [0x89, 0x50, 0x4E, 0x47]);
      expect(nativeImageUri(uri), uri);
      await tester.runAsync(() => deleteNativeStaticMapFile(uri));
      expect(file.existsSync(), isFalse);
    });

    testWidgets('answers null without pins, without a session header, or once no longer current', (tester) async {
      expect(await tester.runAsync(() => resolve(pins: const [])), isNull);
      expect(await tester.runAsync(() => resolve(header: null)), isNull);
      var calls = 0;
      // Current until the file is written, then stale: the written file is deleted.
      expect(await tester.runAsync(() => resolve(current: () => ++calls < 4)), isNull);
      expect(calls, 4);
      expect(directory.listSync(), isEmpty);
    });

    test('never deletes a file it did not write', () async {
      final other = File('${directory.path}/other.png')..writeAsBytesSync([1]);
      await deleteNativeStaticMapFile(Uri.file(other.path).toString());
      expect(other.existsSync(), isTrue);
    });
  });
}
