import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/services.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import '../journeys/support/fixture_backend.dart';
import '../journeys/support/hermetic_boot.dart';

const scenarioNames = ['home_scroll', 'detail_scroll', 'memory_scroll', 'chat_tap'];
final seedDate = DateTime.utc(2026, 9, 16, 9);
int datasetSize(String name, int fallback) {
  final raw = Platform.environment['PERF_$name'] ?? Platform.environment[name];
  final value = raw == null ? fallback : int.tryParse(raw);
  if (value == null || value < 1 || value > 2000) throw ArgumentError('$name must be 1..2000');
  return value;
}

final datasetSizes = {
  'HOME_ITEMS': datasetSize('HOME_ITEMS', 80),
  'DETAIL_MESSAGES': datasetSize('DETAIL_MESSAGES', 100),
  'MEMORY_ITEMS': datasetSize('MEMORY_ITEMS', 60),
  'CHAT_HISTORY': datasetSize('CHAT_HISTORY', 40),
};

/// Adds history/pagination only at the external backend seam. All other routes
/// are delegated to the imported journey fixture, including the real SSE reply.
class PerfWorld {
  static bool _servicesCreated = false;
  late JourneyFixtureBackend backend;
  late HttpServer proxy;
  late Directory nativeDirectory;
  final client = HttpClient();
  late ConversationProvider conversations;
  late MemoriesProvider memories;
  final messages = MessageProvider();

  Future<void> seed() async {
    mockCommonPlatformChannels();
    nativeDirectory = await Directory.systemTemp.createTemp('omi-perf-native-');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMessageHandler(
      'dev.flutter.pigeon.path_provider_foundation.PathProviderApi.getDirectoryPath',
      (_) async => const StandardMessageCodec().encodeMessage([nativeDirectory.path]),
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/connectivity'),
      (_) async => throw MissingPluginException('Host connectivity probe unavailable'),
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/connectivity_status'),
      (_) async => null,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('com.omi/phone_calls/events'), (call) async => null);
    backend = await JourneyHermeticBoot.start();
    if (!_servicesCreated) {
      // init constructs real services before the unavailable hardware probe.
      // Keep its default connectivity state; loopback HTTP remains real.
      try {
        await ServiceManager.init();
      } on MissingPluginException {
        // Host-only hardware I/O boundary.
      }
      _servicesCreated = true;
    }
    for (var i = 0; i < datasetSizes['HOME_ITEMS']!; i++) {
      backend.conversations.add(ServerConversation(
        id: 'perf-conv-$i',
        createdAt: seedDate.subtract(Duration(minutes: i)),
        structured:
            Structured('Performance conversation $i', 'Deterministic summary $i.', emoji: '🧠', category: 'other'),
        transcriptSegments: i == 0
            ? [
                for (var j = 0; j < datasetSizes['DETAIL_MESSAGES']!; j++)
                  TranscriptSegment(
                      id: 'segment-$j',
                      text: 'Deterministic transcript message $j. We discussed the project and its next steps.',
                      speaker: 'SPEAKER_00',
                      isUser: true,
                      personId: null,
                      start: j * 5.0,
                      end: j * 5.0 + 4,
                      translations: [])
              ]
            : [],
      ).toJson());
    }
    for (var i = 0; i < datasetSizes['MEMORY_ITEMS']!; i++) {
      backend.memories.add({
        'id': 'perf-memory-$i',
        'uid': JourneyFixtureBackend.fixtureUid,
        'content': 'Performance memory $i: deterministic project preference and context.',
        'category': 'manual',
        'created_at': seedDate.toIso8601String(),
        'updated_at': seedDate.toIso8601String(),
        'reviewed': true,
        'manually_added': true,
        'visibility': 'private'
      });
    }
    proxy = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    proxy.listen((request) async {
      final path = request.uri.path;
      if (request.method == 'GET' && path == '/v2/apps/search') {
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({
          'data': [],
          'pagination': {'total': 0, 'count': 0, 'offset': 0, 'limit': 50, 'hasNext': false, 'hasPrevious': false},
          'filters': {'sort': 'popular', 'categories': [], 'capabilities': [], 'languages': [], 'deployed_on': []},
        }));
        await request.response.close();
        return;
      }
      if (request.method == 'GET' && ['/v2/messages', '/v3/memories', '/v1/conversations'].contains(path)) {
        final List<Map<String, dynamic>> rows;
        if (path == '/v2/messages') {
          rows = [
            for (var i = 0; i < datasetSizes['CHAT_HISTORY']!; i++)
              {
                'id': 'perf-history-$i',
                'created_at': seedDate.subtract(Duration(minutes: i)).toIso8601String(),
                'text': 'Deterministic history message $i',
                'sender': i.isEven ? 'ai' : 'human',
                'type': 'text',
                'from_integration': false,
                'files': [],
                'files_id': [],
                'memories': [],
              }
          ];
        } else {
          rows = path == '/v3/memories' ? backend.memories : backend.conversations;
        }
        final offset = int.tryParse(request.uri.queryParameters['offset'] ?? '') ?? 0;
        final limit = path == '/v2/messages'
            ? rows.length
            : int.tryParse(request.uri.queryParameters['limit'] ?? '') ?? rows.length;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(rows.skip(offset).take(limit).toList()));
        await request.response.close();
        return;
      }
      final upstream = await client.openUrl(request.method, Uri.parse(backend.baseUrl).resolveUri(request.uri));
      request.headers.forEach((name, values) {
        if (name != HttpHeaders.hostHeader && name != HttpHeaders.contentLengthHeader) {
          upstream.headers.set(name, values);
        }
      });
      await upstream.addStream(request);
      final response = await upstream.close();
      request.response.statusCode = response.statusCode;
      response.headers.forEach((name, values) {
        request.response.headers.set(name, values);
      });
      await request.response.addStream(response);
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${proxy.port}/');
    Env.armDebugJourneyCredentialTrust();
    Env.addDebugTrustedAuthority('127.0.0.1');
    conversations = ConversationProvider(isSignedIn: () => true);
    memories = MemoriesProvider();
    await conversations.forceRefreshConversations();
    while (conversations.hasMoreConversations) {
      if (!await conversations.getMoreConversationsFromServer()) break;
    }
    await memories.loadMemories();
    await messages.refreshMessages();
    expect(conversations.conversations.length, datasetSizes['HOME_ITEMS']);
    expect(memories.memories.length, datasetSizes['MEMORY_ITEMS']);
    expect(messages.messages.length, datasetSizes['CHAT_HISTORY']);
  }

  Future<void> boot(WidgetTester tester) async {
    await JourneyHermeticBoot.pumpPage(tester, page: const Scaffold(), providers: [
      ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
      ChangeNotifierProvider<MessageProvider>.value(value: messages),
      ChangeNotifierProvider(create: (_) => LocalRecordingsProvider()),
      ChangeNotifierProvider(create: (_) => PhoneCallProvider.forTesting()),
      ChangeNotifierProvider(
          create: (_) => DeviceProvider(clock: () => seedDate, chargingConnectionLoader: (_) async => null)),
      ChangeNotifierProvider(create: (_) => SpeakerTagPromptsProvider(now: () => seedDate)),
      ChangeNotifierProvider(create: (_) => CaptureProvider(now: () => seedDate)),
      ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
        create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(seedDate),
        update: (_, app, conversations, previous) => previous!..setProviders(app, conversations),
      ),
    ]);
  }

  Future<void> close() async {
    conversations.dispose();
    memories.dispose();
    messages.dispose();
    client.close(force: true);
    await proxy.close(force: true);
    await backend.stop();
    JourneyHermeticBoot.stop();
    await nativeDirectory.delete(recursive: true);
  }
}

Future<void> pumpFrames(WidgetTester tester, int count) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 16));
  }
}

Future<void> scrollRoundTrip(WidgetTester tester, Type page) async {
  final candidates = find.descendant(
    of: find.byType(page),
    matching: find.byWidgetPredicate(
        (widget) => widget is Scrollable && axisDirectionToAxis(widget.axisDirection) == Axis.vertical),
  );
  final scrollable =
      candidates.evaluate().map((e) => find.byElementPredicate((candidate) => identical(candidate, e))).firstWhere(
            (finder) => tester.state<ScrollableState>(finder).position.maxScrollExtent > 0,
            orElse: () => throw StateError('$page has no vertical scroll extent; '
                '${candidates.evaluate().map((e) => (e as StatefulElement).state).toList()}'),
          );
  final state = tester.state<ScrollableState>(scrollable);
  expect(state.position.maxScrollExtent, greaterThan(0), reason: '$page must contain seeded scroll content');
  for (final direction in [-1.0, 1.0]) {
    for (var n = 0; n < 100; n++) {
      await tester.fling(scrollable, Offset(0, direction * 500), 3000);
      await pumpFrames(tester, 24);
      final pos = state.position;
      if (direction < 0 ? pos.pixels >= pos.maxScrollExtent - 1 : pos.pixels <= pos.minScrollExtent + 1) break;
      if (n == 99) fail('$page did not reach scroll endpoint');
    }
  }
  expect(state.position.pixels, closeTo(state.position.minScrollExtent, 1));
}

Future<void> runScenario(WidgetTester tester, PerfWorld world, String name) async {
  final Widget page = switch (name) {
    'home_scroll' =>
      ConversationsPage(requestInitialLoad: false, loadRecaps: () async => (items: <DailySummary>[], ok: true)),
    'detail_scroll' => ConversationDetailPage(
        conversation: world.conversations.conversations.singleWhere((c) => c.id == 'perf-conv-0'),
        initialTab: ConversationTab.transcript),
    'memory_scroll' => const MemoriesPage(showMindMap: false),
    'chat_tap' => const ChatPage(),
    _ => throw ArgumentError(name),
  };
  globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => page));
  await pumpFrames(tester, 30);
  // Complete real loopback I/O outside the virtual clock, then fixed UI pumps.
  await tester.runAsync(() async {
    await Future<void>.delayed(const Duration(milliseconds: 100));
  });
  await pumpFrames(tester, 10);
  if (name == 'chat_tap') {
    const prompt = 'Summarize the deterministic performance fixture.';
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), prompt);
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.runAsync(() async {
      for (var i = 0; i < 100 && !world.messages.messages.any((m) => m.id.startsWith('srv-reply-')); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
    });
    await pumpFrames(tester, 60);
    expect(world.backend.countOf('POST', '/v2/messages'), 1);
    expect(find.textContaining(world.backend.assistantReplyText), findsWidgets);
  } else {
    await scrollRoundTrip(tester, page.runtimeType);
  }
  globalNavigatorKey.currentState!.pop();
  await pumpFrames(tester, 30);
  expect(find.byType(page.runtimeType), findsNothing);
}
