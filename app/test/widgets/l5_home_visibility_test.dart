import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/live_episode_visibility.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';
import '../helpers/sfpro_font_fixtures.dart';
import '../support/typed_conversation_screen.dart';
import '../support/refactor_flag_adapter.dart';

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String get apiBaseUrl => '';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
}

class _LiveCapture extends CaptureProvider {
  _LiveCapture()
      : super(
            externalActions: const NoopCaptureExternalActions(),
            inProgressConversationLoader: () async {},
            localSegmentStore: LocalSegmentStore.disabled());
  @override
  String? get liveCaptureSource => 'omi';
  @override
  String? get topConversationId => 'active';
}

/// After the episode closed: nothing streams, so Home shows only ordinary rows.
class _IdleCapture extends CaptureProvider {
  _IdleCapture()
      : super(
            externalActions: const NoopCaptureExternalActions(),
            inProgressConversationLoader: () async {},
            localSegmentStore: LocalSegmentStore.disabled());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });
  test('Home hides every live-episode member, whatever its status', () {
    const statuses = ConversationStatus.values;
    final rows = [
      for (final status in statuses)
        ServerConversation(
            id: status.name, createdAt: DateTime.utc(2026), structured: Structured('Synthetic', ''), status: status)
    ];
    final ids = rows.map((row) => row.id).toSet();
    expect(hiddenLiveConversations(ids), ids);
    expect(hiddenLiveConversations({'non_member'}..addAll(ids)), ids.union({'non_member'}));
  });
  for (final serving in [false, true]) {
    testWidgets('live episode folds members under its row; non-members and processing stay (serve=$serving)',
        (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() {
        debugDefaultTargetPlatformOverride = null;
        AnalyticsManager.resetForTesting();
      });
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      VisibilityDetectorController.instance.updateInterval = Duration.zero;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      await tester.runAsync(() => setRefactorFlags({'clients_refactor': serving}));
      final now = DateTime.now();
      final items = [
        for (final id in ['active', 'finished', 'highlight'])
          ServerConversation(
              id: id,
              createdAt: now,
              startedAt: now.subtract(const Duration(minutes: 10)),
              finishedAt: id == 'active' ? null : now,
              structured: Structured(
                  id == 'highlight'
                      ? 'Meeting highlight'
                      : id == 'finished'
                          ? 'Finished meeting'
                          : 'In progress',
                  '',
                  emoji: '',
                  category: 'personal',
                  salience: id == 'highlight' ? 'highlight' : null),
              status: id == 'active' ? ConversationStatus.in_progress : ConversationStatus.completed),
        // A conversation outside the episode keeps its own Home row.
        ServerConversation(
            id: 'other',
            createdAt: now,
            startedAt: now.subtract(const Duration(minutes: 10)),
            finishedAt: now,
            structured: Structured('Phone call', '', emoji: '', category: 'personal'),
            status: ConversationStatus.completed),
      ];
      final conversations =
          ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
            ..conversations = items
            ..groupConversationsByDate()
            ..processingConversations = [
              ServerConversation(
                  id: 'wrapping',
                  createdAt: now,
                  structured: Structured('Wrapping up', '', emoji: '', category: 'personal'),
                  status: ConversationStatus.processing)
            ];
      final live = Episode(
          id: 'episode',
          live: true,
          startedAt: now.subtract(const Duration(hours: 2)),
          lastActivityAt: now,
          title: 'Live episode',
          conversationIds: ['active', 'finished', 'highlight']);
      final episodes = EpisodeProvider(
          fetchPage: (from, to, {cursor}) async => const ApiSuccess(EpisodePageRead(enabled: true)),
          fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)))
        ..debugSetLive(live, enabled: true);
      final capture = _LiveCapture();
      addTearDown(conversations.dispose);
      addTearDown(episodes.dispose);
      addTearDown(capture.dispose);
      final screen = await buildTypedConversationScreen(conversations,
          captureProvider: capture,
          episodes: episodes,
          initializePreferences: false,
          theme: buildOmiTheme(brightness: Brightness.dark));
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(key: boundary, child: screen));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
      // Every member folds under the live row: the split still in progress, the
      // finished one, the highlight. They stay reachable inside the episode page.
      expect(find.text('In progress'), findsNothing);
      expect(find.text('Finished meeting'), findsNothing);
      expect(find.text('Meeting highlight'), findsNothing);
      // The non-member keeps its ordinary row.
      expect(find.text('Phone call'), findsOneWidget);
      expect(find.byType(ConversationListItem), findsOneWidget);
      // A processing member still shows under the live row, as it does today.
      expect(find.byType(ProcessingConversationRow), findsOneWidget);
      expect(find.byKey(const ValueKey('processing_wrapping')), findsOneWidget);
      expect(tester.takeException(), isNull);
      const output = String.fromEnvironment('L5_RENDER_OUTPUT');
      if (output.isNotEmpty) {
        await tester.runAsync(() async {
          final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await render.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory(output).create(recursive: true);
          await File('$output/${serving ? '002' : '001'}-mobile-ios-home-${serving ? 'serve' : 'shadow'}.png')
              .writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      final completed = ServerConversation.fromJson({
        ...items.first.toJson(),
        'status': 'completed',
        'structured': Structured('Just finished', '', category: 'personal').toJson()
      });
      conversations.updateConversationInSortedList(completed);
      await tester.pump();
      // Completing a member does not lift it out of the live episode.
      expect(find.text('Just finished'), findsNothing);
      expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
  testWidgets('a just-closed single processing member appears exactly once on Home', (tester) async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final now = DateTime.now();
    final member = ServerConversation(
        id: 'single-processing',
        createdAt: now,
        startedAt: now,
        structured: Structured('Wrapping up lunch', ''),
        status: ConversationStatus.processing);
    final closed = Episode(
        id: 'closed-single',
        live: false,
        startedAt: now,
        lastActivityAt: now,
        conversationIds: [member.id],
        members: [member]);
    final history = ConversationProvider(isSignedIn: () => true)..processingConversations = [member];
    final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [closed])))
      ..debugSetLive(null)
      ..debugSetHomeEpisodes([closed]);
    final capture = _IdleCapture();
    addTearDown(history.dispose);
    addTearDown(episodes.dispose);
    addTearDown(capture.dispose);
    addTearDown(AnalyticsManager.resetForTesting);
    final screen = await buildTypedConversationScreen(history,
        captureProvider: capture, episodes: episodes, initializePreferences: false);
    await tester.pumpWidget(screen);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(ConversationListItem), findsNothing);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(find.text('Wrapping up lunch'), findsOneWidget);
    final completed = ServerConversation.fromJson({...member.toJson(), 'status': 'completed'});
    history.removeProcessingConversation(member.id);
    await history.addConversation(completed);
    await tester.pump();
    expect(find.byType(ProcessingConversationRow), findsNothing);
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final searching in [false, true]) {
    testWidgets('closed episode Home and search open the episode page (search=$searching)', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() {
        debugDefaultTargetPlatformOverride = null;
        AnalyticsManager.resetForTesting();
      });
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      VisibilityDetectorController.instance.updateInterval = Duration.zero;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      final now = DateTime.now();
      final items = [
        for (final id in ['active', 'finished'])
          ServerConversation(
              id: id,
              createdAt: now,
              startedAt: now.subtract(const Duration(minutes: 10)),
              finishedAt: id == 'active' ? null : now,
              structured: Structured(id == 'finished' ? 'Finished meeting' : 'Was in progress', '',
                  emoji: '', category: 'personal'),
              status: id == 'active' ? ConversationStatus.in_progress : ConversationStatus.completed)
      ];
      final conversations =
          ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
            ..conversations = items
            ..groupConversationsByDate();
      final closed = Episode(
          id: 'closed',
          live: false,
          startedAt: now.subtract(const Duration(minutes: 10)),
          lastActivityAt: now,
          title: 'Planning the garden',
          conversationIds: ['active', 'finished'],
          members: items);
      if (searching) conversations.previousQuery = 'meeting';
      // The closed snapshot owns both members even with no streaming capture.
      final episodes = EpisodeProvider(
          fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [closed])),
          fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true, episode: null)),
          lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: closed)))
        ..debugSetLive(null, enabled: true)
        ..debugSetHomeEpisodes([closed]);
      final capture = _IdleCapture();
      addTearDown(conversations.dispose);
      addTearDown(episodes.dispose);
      addTearDown(capture.dispose);
      final screen = await buildTypedConversationScreen(conversations,
          captureProvider: capture,
          episodes: episodes,
          initializePreferences: false,
          theme: buildOmiTheme(brightness: Brightness.dark));
      await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(value: conversations, child: screen));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const Key('home_live_episode_row')), findsNothing);
      if (searching) {
        expect(find.text('Planning the garden'), findsNothing);
        await tester.tap(find.text('Finished meeting'));
      } else {
        expect(find.text('Finished meeting'), findsNothing);
        expect(find.text('Was in progress'), findsNothing);
        expect(find.text('Planning the garden'), findsOneWidget);
        expect(find.textContaining('2 parts'), findsOneWidget);
        expect(find.byType(ConversationListItem), findsOneWidget);
        final row = find.byType(ConversationListItem);
        expect(find.descendant(of: row, matching: find.text('10m')), findsOneWidget);
        expect(find.descendant(of: row, matching: find.text(' • ')), findsNWidgets(2));
        await tester.tap(find.text('Planning the garden'));
      }
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('episode_page')), findsOneWidget);
      expect(find.text('Finished meeting'), findsOneWidget);
      expect(find.text('Was in progress'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
