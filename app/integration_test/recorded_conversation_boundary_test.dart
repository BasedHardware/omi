// Native replay of sanitized planner output. No production backend or customer writes.
// Serve canonical-replay-sanitized.json on loopback, then pass its URL through
// --dart-define=RECORDED_BOUNDARY_FIXTURE_URL=http://127.0.0.1:<port>/<file>.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';

import 'journeys/support/hermetic_boot.dart';
import 'visual_audit/fakes.dart';
import 'visual_audit/harness.dart' show LoopbackOnly, loadAuditFonts;
import 'visual_audit/scenarios/capture.dart' show AuditCaptureProvider, AuditLive;

const _fixtureUrl = String.fromEnvironment('RECORDED_BOUNDARY_FIXTURE_URL');

class _ExportPath extends PathProviderPlatform {
  _ExportPath(this.path);
  final String path;
  @override
  Future<String> getTemporaryPath() async => path;
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('recorded windows stay isolated through Home, Summary, Transcript and Select', (tester) async {
    final fixtureUri = Uri.parse(_fixtureUrl);
    expect(fixtureUri.isScheme('http') && fixtureUri.host == '127.0.0.1', isTrue);
    HttpOverrides.global = LoopbackOnly();
    final client = HttpClient();
    final request = await client.getUrl(fixtureUri);
    final response = await request.close();
    expect(response.statusCode, 200);
    final fixture = jsonDecode(await utf8.decoder.bind(response).join()) as Map<String, dynamic>;
    client.close(force: true);
    final rows = (fixture['conversations'] as List).cast<Map<String, dynamic>>();
    final speakers = fixture['recording_transcripts'] as Map<String, dynamic>;
    final familyId = fixture['family_id'] as String;
    final fundraisingIds = (fixture['fundraising_ids'] as List).cast<String>();
    expect(rows, hasLength(4), reason: 'the frozen replay includes its real quiet gap and existing two-hour cap');

    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, _) async => method == 'getRevision' ? 1 : null;
    final server = await JourneyHermeticBoot.start();
    server.conversations.addAll(rows.reversed);
    for (var i = 0; i < 20; i++) {
      server.failNext('GET', '/v1/conversations/live', status: 200, body: '{"v3":true,"conversation":null}');
      for (final id in [familyId, ...fundraisingIds]) {
        server.failNext('GET', '/v1/conversations/$id/recording-speakers', status: 200, body: jsonEncode(speakers[id]));
      }
    }
    final history = ConversationProvider(isSignedIn: () => true);
    final v3 = ConversationsV3Provider();
    final episodes = EpisodeProvider()..suppressed = () => v3.suppressesLegacy;
    final feed = HomeFeedProvider()..suppressed = () => v3.suppressesLegacy;
    final apps = AppProvider();
    final detail = ConversationDetailProvider()..setProviders(apps, history);
    final capture = AuditCaptureProvider(AuditLive.idle);
    final pending = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    final exports = await Directory.systemTemp.createTemp('omi-boundary-export-');
    final previousPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _ExportPath(exports.path);
    final shares = <MethodCall>[];
    const shareChannel = MethodChannel('dev.fluttercommunity.plus/share');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(shareChannel, (call) async {
      shares.add(call);
      return 'dev.fluttercommunity.plus/share/success';
    });
    addTearDown(() async {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(shareChannel, null);
      PathProviderPlatform.instance = previousPaths;
      await exports.delete(recursive: true);
      await server.stop();
      JourneyHermeticBoot.stop();
      SharedPreferencesUtil.capturePolicyBridgeForTesting = null;
      detail.dispose();
      history.dispose();
      v3.dispose();
      episodes.dispose();
      feed.dispose();
      apps.dispose();
      capture.dispose();
    });
    await v3.refresh();
    await history.forceRefreshConversations();
    expect(v3.v3, isTrue);
    expect(history.conversations.map((c) => c.id).toSet(), rows.map((c) => c['id']).toSet());
    await loadAuditFonts();
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    await JourneyHermeticBoot.pumpPage(tester,
        page: ConversationsPage(
          requestInitialLoad: false,
          loadRecaps: () async => (items: <DailySummary>[], ok: true),
          pendingWork: pending,
        ),
        providers: [
          ...defaultAuditProviders(),
          ChangeNotifierProvider<ConversationProvider>.value(value: history),
          ChangeNotifierProvider<ConversationsV3Provider>.value(value: v3),
          ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
          ChangeNotifierProvider<HomeFeedProvider>.value(value: feed),
          ChangeNotifierProvider<AppProvider>.value(value: apps),
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ],
        appBuilder: (page) => MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: buildOmiTheme(brightness: Brightness.light),
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              home: Scaffold(body: SafeArea(child: page)),
            ));

    Future<void> settle() async {
      for (var i = 0; i < 8; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 70));
        await tester.pump();
      }
      expect(tester.takeException(), isNull);
    }

    Future<void> frame(String name) async {
      await settle();
      debugPrint('BOUNDARY_FRAME $name');
      await binding.takeScreenshot(name);
      await Future<void>.delayed(const Duration(seconds: 2));
    }

    Future<void> open(String id) async {
      final row = find.byWidgetPredicate((w) => w is ConversationListItem && w.conversation.id == id);
      await tester.ensureVisible(row);
      await tester.tap(row);
      await settle();
      expect(find.byType(ConversationDetailPage), findsOneWidget);
      expect(find.byType(EpisodePage), findsNothing);
      expect(detail.conversation.id, id);
    }

    Future<void> back() async {
      await tester.tap(find.byType(OmiBackButton).first);
      await settle();
      expect(find.byType(ConversationDetailPage), findsNothing);
    }

    await frame('01-home');
    final checks = <Map<String, Object>>[];
    for (var cycle = 0; cycle < 3; cycle++) {
      await open(familyId);
      expect(detail.conversation.structured.overview, contains('FAMILY_SENTINEL'));
      await back();
      final id = fundraisingIds[cycle];
      await open(id);
      expect(detail.conversation.structured.overview, contains('FUNDRAISING_SENTINEL'));
      expect(find.text('Family conversation'), findsNothing);
      expect(find.byKey(const Key('conversation_tab_summary')), findsOneWidget);
      await frame('02-summary-${cycle + 1}');
      await tester.tap(find.byKey(const Key('conversation_tab_transcript')));
      await settle();
      expect(find.textContaining('FUNDRAISING_SENTINEL', findRichText: true), findsWidgets);
      expect(find.textContaining('FAMILY_SENTINEL', findRichText: true), findsNothing);
      await tester.tap(find.byKey(const Key('transcript_select_lines')));
      await settle();
      expect(server.countOf('GET', '/v1/conversations/$id/recording-speakers'), greaterThanOrEqualTo(1));
      expect(detail.recordingLoadFailed, isFalse);
      expect(detail.hasRecordingSiblings, isFalse);
      expect(detail.recordingSegments, hasLength(detail.conversation.transcriptSegments.length));
      expect(detail.recordingSegments.every((s) => !s.text.contains('FAMILY_SENTINEL')), isTrue);
      await frame('03-transcript-select-${cycle + 1}');
      await tester.tap(find.byKey(const Key('speaker_labeling_cancel_selection')));
      await settle();
      await tester.tap(find.byKey(const Key('speaker_labeling_done')));
      await settle();
      await tester.tap(find.byKey(const Key('conversation_more')));
      await settle();
      expect(find.text('Export Transcript'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
      // This observed replay contains no audio files; do not invent playback evidence for it.
      expect(detail.conversation.audioFiles, isEmpty);
      expect(find.text('Share Audio'), findsNothing);
      await tester.tap(find.text('Export Transcript'));
      await settle();
      expect(shares, hasLength(cycle + 1));
      final file = File('${exports.path}/transcript_exports/${conversationTranscriptFileName(detail.conversation)}');
      final exported = await file.readAsString();
      expect(exported, contains('FUNDRAISING_SENTINEL'));
      expect(exported, isNot(contains('FAMILY_SENTINEL')));
      checks.add({
        'id': id,
        'lines': detail.recordingSegments.length,
        'duration_seconds': detail.conversation.getDurationInSeconds()
      });
      await back();
    }
    expect(server.requestCounts.keys.where((k) => k.contains('/episodes') || k.contains('/home/feed')), isEmpty);
    binding.reportData = {
      ...?binding.reportData,
      'source_sha': fixture['source_sha'],
      'evidence_kind': fixture['evidence_kind'],
      'window_checks': checks,
      'exports': shares.length,
      'physical_device_qualified': false
    };
    debugPrint('BOUNDARY_REPLAY_PASSED ${jsonEncode(checks)}');
    await frame('04-home-complete');
    await tester.pumpWidget(const SizedBox.shrink());
  }, skip: _fixtureUrl.isEmpty);
}
