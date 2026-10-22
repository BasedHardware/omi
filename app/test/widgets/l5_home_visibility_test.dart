import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
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
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';
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
      loader.addFont(rootBundle.load('assets/fonts/SFPRODISPLAY$weight.OTF'));
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });
  test('serving Home hides in-progress, processing and merging until a terminal outcome', () {
    final statuses = [
      ConversationStatus.in_progress,
      ConversationStatus.processing,
      ConversationStatus.merging,
      ConversationStatus.completed,
      ConversationStatus.failed
    ];
    final rows = [
      for (final status in statuses)
        ServerConversation(
            id: status.name, createdAt: DateTime.utc(2026), structured: Structured('Synthetic', ''), status: status)
    ];
    final ids = rows.map((row) => row.id).toSet();
    expect(hiddenLiveConversations(ids, rows, serving: false), ids);
    expect(hiddenLiveConversations(ids, rows, serving: true), {'in_progress', 'processing', 'merging'});
  });
  for (final serving in [false, true]) {
    testWidgets('real Home keeps finished episode rows and highlights (serve=$serving)', (tester) async {
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
              status: id == 'active' ? ConversationStatus.in_progress : ConversationStatus.completed)
      ];
      final conversations =
          ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
            ..conversations = items
            ..groupConversationsByDate();
      final live = Episode(
          id: 'episode',
          live: true,
          startedAt: now.subtract(const Duration(hours: 2)),
          lastActivityAt: now,
          title: 'Live episode',
          conversationIds: items.map((c) => c.id).toList());
      final episodes = EpisodeProvider(fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)))
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
      expect(find.text('In progress'), findsNothing);
      expect(find.text('Finished meeting'), serving ? findsOneWidget : findsNothing);
      expect(find.text('Meeting highlight'), serving ? findsOneWidget : findsNothing);
      expect(find.byType(ConversationListItem), serving ? findsNWidgets(2) : findsNothing);
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
      expect(find.text('Just finished'), serving ? findsOneWidget : findsNothing);
      expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
