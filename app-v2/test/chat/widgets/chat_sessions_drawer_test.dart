import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/chat/widgets/chat_sessions_drawer.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/chat_service.dart';

class _FakePathProvider extends PathProviderPlatform {
  _FakePathProvider(this.tempDir);
  final String tempDir;
  @override
  Future<String?> getApplicationDocumentsPath() async => tempDir;
  @override
  Future<String?> getApplicationSupportPath() async => tempDir;
  @override
  Future<String?> getTemporaryPath() async => tempDir;
}

/// Minimal stub `ChatService` — the drawer doesn't trigger streaming, but
/// `ChatProvider` requires a service in its constructor.
class _StubChatService extends ChatService {
  _StubChatService()
      : super(
          client: ApiClient(
            httpClient: MockClient((_) async => http.Response('', 200)),
            getIdToken: ({bool forceRefresh = false}) async => 'tok',
            signOut: () async {},
            baseUrl: 'https://example.test/',
          ),
        );

  @override
  Stream<ChatStreamEvent> streamChat(String prompt) =>
      const Stream<ChatStreamEvent>.empty();
}

/// Wraps the drawer in a Scaffold + ChangeNotifierProvider so the test can
/// open it via a `GlobalKey<ScaffoldState>`.
Widget _harness(ChatProvider provider, GlobalKey<ScaffoldState> scaffoldKey) {
  return MaterialApp(
    home: ChangeNotifierProvider<ChatProvider>.value(
      value: provider,
      child: Scaffold(
        key: scaffoldKey,
        drawer: const ChatSessionsDrawer(),
        body: const SizedBox.expand(),
      ),
    ),
  );
}

/// Pumps a series of fixed-duration frames. We avoid `pumpAndSettle` because
/// the drawer's InkWell ripple animations keep emitting frames, which makes
/// settle() spin indefinitely. 10 × 100ms covers all drawer-open / drawer-
/// close / Navigator.pop animations in the Material drawer.
Future<void> _pumpFrames(WidgetTester tester,
    {int count = 10, int ms = 100}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(Duration(milliseconds: ms));
  }
}

void main() {
  late Directory tempDir;

  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  // Per-test Hive isolation — each test gets a fresh temp dir + Hive instance
  // so fire-and-forget `_persistSession` futures from a prior test can't
  // deadlock the next test's setUp clear/open calls.
  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('chat_drawer_test');
    PathProviderPlatform.instance = _FakePathProvider(tempDir.path);
    Hive.init(tempDir.path);
    await Hive.openBox<Map>(ChatBoxes.messages);
    await Hive.openBox<Map>(ChatBoxes.sessions);
  });

  tearDown(() async {
    try {
      await Hive.close().timeout(const Duration(seconds: 2));
    } catch (_) {
      // Best-effort — fresh tempDir next test means stale state is harmless.
    }
    if (tempDir.existsSync()) {
      await tempDir.delete(recursive: true);
    }
  });

  testWidgets(
      'pinned sessions render in PINNED group above date buckets',
      (tester) async {
    final provider = ChatProvider(service: _StubChatService());
    addTearDown(() {
      provider.dispose();
    });

    // Seed three sessions, all created today. Rename each so titles are
    // unique and don't collide with the "+ New chat" button label.
    final aId = provider.newSession();
    await provider.renameSession(aId, 'Alpha session');
    final bId = provider.newSession();
    await provider.renameSession(bId, 'Bravo pinned');
    final cId = provider.newSession();
    await provider.renameSession(cId, 'Charlie session');

    // Pin session B — renders under PINNED, the others under TODAY.
    await provider.togglePin(bId);

    final scaffoldKey = GlobalKey<ScaffoldState>();
    await tester.pumpWidget(_harness(provider, scaffoldKey));
    await _pumpFrames(tester, count: 5, ms: 50);

    scaffoldKey.currentState!.openDrawer();
    await _pumpFrames(tester);

    // Group labels visible — PINNED + TODAY only, no other date buckets.
    expect(find.text('PINNED'), findsOneWidget);
    expect(find.text('TODAY'), findsOneWidget);
    expect(find.text('YESTERDAY'), findsNothing);
    expect(find.text('THIS WEEK'), findsNothing);
    expect(find.text('OLDER'), findsNothing);

    // PINNED label must appear visually above TODAY label (lower y = higher).
    final pinnedY = tester.getTopLeft(find.text('PINNED')).dy;
    final todayY = tester.getTopLeft(find.text('TODAY')).dy;
    expect(pinnedY, lessThan(todayY),
        reason: 'PINNED group must render above TODAY');

    // All three session rows are present.
    final bRow = find.text('Bravo pinned');
    final aRow = find.text('Alpha session');
    final cRow = find.text('Charlie session');
    expect(bRow, findsOneWidget);
    expect(aRow, findsOneWidget);
    expect(cRow, findsOneWidget);

    // Pinned row B sits between PINNED label and TODAY label.
    final bRowY = tester.getTopLeft(bRow).dy;
    expect(bRowY, greaterThan(pinnedY),
        reason: 'pinned session row must be below the PINNED label');
    expect(bRowY, lessThan(todayY),
        reason: 'pinned session row must be above the TODAY label');

    // Unpinned A and C render under TODAY (below the TODAY label).
    expect(tester.getTopLeft(aRow).dy, greaterThan(todayY),
        reason: 'unpinned session A renders under TODAY');
    expect(tester.getTopLeft(cRow).dy, greaterThan(todayY),
        reason: 'unpinned session C renders under TODAY');

  });

  testWidgets(
      'tap "+ New chat" button calls provider.newSession() and pops drawer',
      (tester) async {
    final provider = ChatProvider(service: _StubChatService());
    addTearDown(() {
      provider.dispose();
    });

    // Seed one session, renamed so its row doesn't collide with the
    // "+ New chat" button label.
    final id = provider.newSession();
    await provider.renameSession(id, 'Existing thread');
    expect(provider.sessions, hasLength(1));

    final scaffoldKey = GlobalKey<ScaffoldState>();
    await tester.pumpWidget(_harness(provider, scaffoldKey));
    await _pumpFrames(tester, count: 5, ms: 50);

    scaffoldKey.currentState!.openDrawer();
    await _pumpFrames(tester);

    expect(scaffoldKey.currentState!.isDrawerOpen, isTrue);

    // Tap the "+ New chat" button — the only widget showing this exact text
    // now that the seeded session has been renamed.
    await tester.tap(find.text('New chat'));
    await _pumpFrames(tester, count: 15, ms: 100);

    expect(provider.sessions, hasLength(2),
        reason: 'tapping New chat creates a new session');
    expect(scaffoldKey.currentState!.isDrawerOpen, isFalse,
        reason: 'drawer should be popped after New chat tap');

  });

  testWidgets(
      'tap a session row calls provider.selectSession() and pops drawer',
      (tester) async {
    final provider = ChatProvider(service: _StubChatService());
    addTearDown(() {
      provider.dispose();
    });

    // Create A first then B — newSession() makes B the active one.
    final aId = provider.newSession();
    final bId = provider.newSession();
    expect(provider.currentSessionId, bId);

    // Rename A so its title is unique and easy to tap.
    final renamed = await provider.renameSession(aId, 'Session Alpha');
    expect(renamed, isTrue);

    final scaffoldKey = GlobalKey<ScaffoldState>();
    await tester.pumpWidget(_harness(provider, scaffoldKey));
    await _pumpFrames(tester, count: 5, ms: 50);

    scaffoldKey.currentState!.openDrawer();
    await _pumpFrames(tester);

    expect(scaffoldKey.currentState!.isDrawerOpen, isTrue);

    // Tap session A's title row.
    await tester.tap(find.text('Session Alpha'));
    await _pumpFrames(tester, count: 15, ms: 100);

    expect(provider.currentSessionId, aId,
        reason: 'tapping a session row selects it');
    expect(scaffoldKey.currentState!.isDrawerOpen, isFalse,
        reason: 'drawer should be popped after row tap');

  });
}
