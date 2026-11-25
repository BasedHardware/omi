import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart' show ConversationByIdResult;
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/widgets/transcript.dart';
import '../support/live_preview_fakes.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../helpers/transcription_hold_wire.dart';

/// Set to write the legacy-page PR evidence (UI-Evidence) PNGs here.
const _evidence = String.fromEnvironment('OMI_Q12_EVIDENCE_DIR');
final _boundary = GlobalKey();

/// The page's MessageListener branch for REPROCESS_TRANSCRIPTION_PENDING and the Summary tab's
/// empty state, driven with the real held-recording wire copies (`../helpers/transcription_hold_wire.dart`)
/// and the real reprocess call answering 409 `transcription_pending`.
Future<(ConversationDetailProvider, AppLocalizations)> _pumpPage(
  WidgetTester tester,
  ServerConversation initial, {
  ServerConversation? fetched,
  ConversationTab? tab = ConversationTab.summary,
  CaptureProvider? capture,
  ConversationsV3Provider? v3,
  bool firstFrameOnly = false,
  Future<ConversationByIdResult> Function(String)? fetchResult,
}) async {
  final conversations = ConversationProvider(isSignedIn: () => false)
    ..conversations = [initial]
    ..groupedConversations = {
      conversationLocalDayKey(initial.createdAt): [initial],
    }
    ..conversationDetailsFetcherOverride = (_) async => fetched ?? initial;
  final apps = AppProvider();
  final detail = ConversationDetailProvider(
    reprocess: heldWireReprocess(409, heldReprocess409Body),
    fetchConversation: (_) async => fetched ?? initial,
    fetchConversationResult: fetchResult,
  )..setProviders(apps, conversations);
  addTearDown(() {
    detail.dispose();
    conversations.dispose();
    apps.dispose();
  });
  await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: OmiColors.active == OmiPalette.light ? Brightness.light : Brightness.dark),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: MultiProvider(
          providers: [
            if (capture != null) ChangeNotifierProvider<CaptureProvider>.value(value: capture),
            if (v3 != null) ChangeNotifierProvider<ConversationsV3Provider>.value(value: v3),
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider<AppProvider>.value(value: apps),
            ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (_) => PeopleProvider()),
            ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {},
              ),
            ),
          ],
          child: ConversationDetailPage(conversation: initial, initialTab: tab),
        ),
      )));
  if (!firstFrameOnly) await _settle(tester);
  final l10n = AppLocalizations.of(tester.element(find.byType(ConversationDetailPage)));
  return (detail, l10n);
}

/// Captures the page as it renders on an iPhone for the PR's UI evidence; a no-op in CI.
Future<void> _captureEvidence(WidgetTester tester, String name) async {
  if (_evidence.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_boundary));
    final image = await boundary.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final dir = await Directory(_evidence).create(recursive: true);
    await File('${dir.path}/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Future<void> _loadEvidenceFonts() async {
  final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
  for (final entry in fonts) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List<dynamic>) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in const [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10 && dir.path != dir.parent.path; i++, dir = dir.parent) {
    final icons = File('${dir.path}/artifacts/material_fonts/MaterialIcons-Regular.otf');
    if (!icons.existsSync()) continue;
    final loader = FontLoader('MaterialIcons')
      ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(icons.readAsBytesSync()))));
    await loader.load();
    return;
  }
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

Future<void> _drain(WidgetTester tester) async {
  // Let any feedback timer run out before the test ends.
  await tester.pump(const Duration(seconds: 10));
  await tester.pumpWidget(const SizedBox());
}

/// Title text drawn at rest (the editable field underneath also holds the stored title).
Finder _shownTitle(String text) => find.byWidgetPredicate((w) => w is Text && w.data == text);

class _LiveCapture extends ChangeNotifier implements CaptureProvider {
  _LiveCapture(this.livePreview, this.recordingId, this.ownerUid);
  @override
  final LivePreviewController livePreview;
  String? recordingId;
  void updateRecordingProof(String? id) {
    recordingId = id;
    notifyListeners();
  }

  final String ownerUid;
  @override
  List<TranscriptSegment> get segments => const [];
  @override
  Iterable<String> get locallyReceivedSegmentIds => const [];
  @override
  bool get isPhoneMicBatchRecording => false;
  @override
  String? get liveCaptureSource => 'omi';
  @override
  String? get activeRecordingId => null;
  @override
  bool get pendantCaptureVerified => true;
  @override
  bool get localPreviewAdmitted => true;
  @override
  String? get verifiedLiveServerRecordingId => SharedPreferencesUtil().uid == ownerUid ? recordingId : null;
  @override
  bool hasClosedServerRecording(String recordingId) => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(initHeldWireEnv);
  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    TranscriptionPendingConversations.reset();
  });
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
    TranscriptionPendingConversations.reset();
  });

  Future<void> expectNoticeOnly(WidgetTester tester, AppLocalizations l10n) async {
    expect(find.byKey(const Key('conversation_detail_transcription_pending')), findsOneWidget);
    // The notice is the only place the body appears: no duplicate message.
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.generateSummary), findsNothing);
    expect(find.text(l10n.retry), findsNothing);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    // The header no longer says "Couldn't transcribe" above a notice that the summary is coming.
    expect(_shownTitle(TranscriptionPendingConversations.serverHoldTitle), findsNothing);
  }

  test('listen session requires the exact client recording identifier', () {
    final payload = {'type': 'conversation_session', 'conversation_id': 'raw-1', 'status': 'in_progress'};
    expect(MessageEvent.fromJson(payload), isA<UnknownEvent>());
    final event = MessageEvent.fromJson({...payload, 'recording_session_id': 'capture-1'}) as ConversationSessionEvent;
    expect(event.clientSessionId, 'capture-1');
    expect(event.recordingId, 'raw-1');
  });

  for (final scenario in [
    'verified',
    'other recording',
    'other account',
    'locked',
    'no lineage',
    'denied',
    'offline'
  ]) {
    testWidgets('LIVE route first frame and hydration with $scenario', (tester) async {
      SharedPreferencesUtil().uid = 'account';
      SummaryGenerationV2Gate.debugOverride = false;
      final origin = DateTime.utc(2026, 11, 18);
      final engine = FakeLivePreviewEngine();
      final preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
      )..admit(language: 'en');
      final capture = _LiveCapture(preview, scenario == 'other recording' ? 'raw-other' : 'raw-1', 'account');
      final v3 = ConversationsV3Provider(
        fetchLive: () async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
        cached: 'account:1',
        uid: () => 'account',
      );
      addTearDown(preview.dispose);
      addTearDown(capture.dispose);
      addTearDown(v3.dispose);
      await tester.pump();
      engine.emit('earlier', 'Earlier window must stay private', true,
          startedAt: origin.subtract(const Duration(seconds: 5)), endedAt: origin);
      engine.emit('verified', 'The agenda is ready for review.', true,
          startedAt: origin.add(const Duration(seconds: 1)), endedAt: origin.add(const Duration(seconds: 3)));
      ServerConversation row({bool withLines = false}) => ServerConversation.fromJson({
            ...heldDetail().toJson(),
            'status': 'in_progress',
            'started_at': origin.toIso8601String(),
            'tile_state': 'live',
            'v3_derived': true,
            'is_locked': scenario == 'locked',
            if (scenario != 'no lineage') 'v3_recording_ids': ['raw-1'],
            'transcript_segments': [
              if (withLines)
                for (var index = 0; index < 42; index++)
                  {
                    'id': 'speech-$index',
                    'text': 'Final line $index, a separate discussion point.',
                    'start': 4 + index * 2,
                    'end': 5 + index * 2,
                    'speaker': index.isEven ? 'SPEAKER_00' : 'SPEAKER_01',
                    'is_user': index.isEven,
                    'translations': [],
                  },
            ],
          });
      if (scenario == 'other account') SharedPreferencesUtil().uid = 'another-account';
      if (scenario == 'verified' && _evidence.isNotEmpty) {
        await tester.runAsync(_loadEvidenceFonts);
        final previousPalette = OmiColors.active;
        OmiColors.active = OmiPalette.light;
        addTearDown(() => OmiColors.active = previousPalette);
        tester.view.physicalSize = const Size(393 * 3, 852 * 3);
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.reset);
      }
      final (detail, _) = await _pumpPage(
        tester,
        row(),
        capture: capture,
        v3: v3,
        fetched: row(),
        fetchResult: (_) async => switch (scenario) {
          'denied' => (item: null, ok: true, inaccessible: true),
          'offline' => (item: null, ok: false, inaccessible: false),
          _ => (item: row(), ok: true, inaccessible: false),
        },
        tab: null,
        firstFrameOnly: true,
      );
      final text = find.text('The agenda is ready for review.');
      expect(text, ['verified', 'denied', 'offline'].contains(scenario) ? findsOneWidget : findsNothing);
      expect(find.text('Earlier window must stay private'), findsNothing);
      if (scenario == 'verified') await _captureEvidence(tester, 'live-transcript-first-frame');
      await _settle(tester);
      expect(text, ['verified', 'offline'].contains(scenario) ? findsOneWidget : findsNothing);
      if (scenario == 'verified') {
        await _captureEvidence(tester, 'live-transcript-hydrated');
        capture.updateRecordingProof('another-window');
        await _settle(tester);
        expect(text, findsNothing);
        capture.updateRecordingProof('raw-1');
        await _settle(tester);
        expect(text, findsOneWidget);
        detail.setCachedConversation(row(withLines: true));
        await _settle(tester);
        final list = find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(Scrollable)).first;
        await tester.drag(list, const Offset(0, -500));
        await _settle(tester);
        final position = tester.state<ScrollableState>(list).position;
        final before = position.pixels;
        expect(before, greaterThan(100));
        detail.setCachedConversation(row(withLines: true));
        await _settle(tester);
        expect(tester.state<ScrollableState>(list).position.pixels, closeTo(before, 2));
        detail.setCachedConversation(row());
        SharedPreferencesUtil().uid = 'another-account';
        capture.updateRecordingProof('raw-1');
        await _settle(tester);
        expect(text, findsNothing);
      }
      preview.endCapture();
      await _drain(tester);
    });
  }

  testWidgets('legacy, opened from the Home row: after the 409 the tab shows the notice and no action', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    // The list row (a) opens the page; the detail read lands copy (b), which has no Home step.
    final (detail, l10n) = await _pumpPage(tester, heldListRow(), fetched: heldDetail());
    expect(await detail.refreshConversation(), isTrue);
    await _settle(tester);
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    await expectNoticeOnly(tester, l10n);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy, cached detail copy: Generate Summary gives way to the notice after the 409', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    if (_evidence.isNotEmpty) {
      await tester.runAsync(_loadEvidenceFonts);
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393 * 3, 852 * 3);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
      final previousPalette = OmiColors.active;
      OmiColors.active = OmiPalette.dark;
      addTearDown(() => OmiColors.active = previousPalette);
    }
    final (detail, l10n) = await _pumpPage(tester, heldDetail());
    // Before any answer the server copy alone offers Generate Summary under its stand-in title.
    expect(find.text(l10n.generateSummary), findsOneWidget);
    expect(_shownTitle(TranscriptionPendingConversations.serverHoldTitle), findsOneWidget);
    await tester.tap(find.text(l10n.generateSummary));
    await _settle(tester);
    expect(TranscriptionPendingConversations.contains(heldConversationId), isTrue);
    await expectNoticeOnly(tester, l10n);
    await _captureEvidence(tester, '001-mobile-ios-legacy-detail-transcription-pending');
    debugDefaultTargetPlatformOverride = null;
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy, Transcript tab open: it says so once, not as an error', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, heldDetail(), tab: ConversationTab.transcript);
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy: a pending answer for another conversation says nothing here', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, heldDetail(), tab: ConversationTab.transcript);
    detail.lastFailedReprocessConversationId = 'another-conversation';
    detail.notifyInfo('REPROCESS_TRANSCRIPTION_PENDING');
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsNothing);
    await _drain(tester);
  });

  testWidgets('redesign: the Summary card explains it in place with no extra message', (tester) async {
    SummaryGenerationV2Gate.debugOverride = true;
    final (detail, l10n) = await _pumpPage(tester, heldListRow(), fetched: heldDetail());
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingTitle), findsOneWidget);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });
}
