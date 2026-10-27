import 'dart:async';
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

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_notes.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../support/live_preview_fakes.dart';

/// Every state of the local-preview surfaces, iOS and Android, light and dark: the
/// transcript (preview lines, hybrid final+preview, no-engine card), the
/// Summary tab's Live card and on-device notes, the Home live row and the Home
/// capture card's last-line slot. `--dart-define=OMI_LIVE_PREVIEW_EVIDENCE_DIR=<dir>`
/// writes the PR's evidence set (iOS light at 390×844, plus one dark Summary);
/// without it this is a layout/overflow/copy check only.
const _evidence = String.fromEnvironment('OMI_LIVE_PREVIEW_EVIDENCE_DIR');

/// iOS's largest accessibility text size (AX5) scales body text about 3.1×.
const _largestTextScale = 3.1;

class _Device extends ChangeNotifier implements DeviceProvider {
  static final _pendant = BtDevice(id: 'omi', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => _pendant;
  @override
  BtDevice? get pairedDevice => _pendant;
  @override
  bool get isConnecting => false;
  @override
  int get batteryLevel => 0;
  @override
  bool get isCharging => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Call extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;
  @override
  List<TranscriptSegment> get transcriptSegments => const [];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Ble implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _PhoneSync {
  int inFlightSeconds = 0;
  int getInFlightSeconds() => inFlightSeconds;
  List<dynamic> getSessionUnsyncedWals(int start) => const [];
  List<dynamic> getSessionWals(int start) => const [];
}

class _Syncs {
  final phone = _PhoneSync();
}

class _Wal implements IWalService {
  _Wal(this.syncs);
  final _Syncs syncs;
  @override
  dynamic getSyncs() => syncs;
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// A real CaptureProvider recording from the pendant, with the admission and
/// the preview model injected (the socket path is covered by the routing tests).
class _Capture extends CaptureProvider {
  _Capture({this.preview, this.admitted = false, int inFlightSeconds = 0})
      : super(
          walService: _Wal(_Syncs()..phone.inFlightSeconds = inFlightSeconds),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _Ble(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  final LivePreviewController? preview;
  final bool admitted;

  @override
  LivePreviewController? get livePreview => preview;
  @override
  bool get localPreviewAdmitted => admitted;
  @override
  DateTime? get liveTranscriptStartedAt => DateTime.utc(2026, 10, 27);
  @override
  String? get liveCaptureSource => 'omi';
  @override
  bool get pendantCaptureVerified => true;
  @override
  bool get transcriptServiceReady => true;
  @override
  RecordingState get recordingState => RecordingState.deviceRecord;
  @override
  bool get havingRecordingDevice => true;
}

enum _State { streaming, starting, listening, noEngine, hybrid, cloud, notes, notesUnavailable }

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  final t0 = DateTime.utc(2026, 10, 22, 2, 18);

  Episode episodeWith({List<String> bullets = const [], String title = 'Meeting Prep', String id = 'ep1'}) => Episode(
      id: id,
      live: true,
      startedAt: t0,
      lastActivityAt: t0,
      title: title,
      bullets: bullets,
      conversationIds: const ['c1']);

  EpisodeProvider episodesWith(Episode episode, {DateTime? now}) => EpisodeProvider(
        clock: () => now ?? DateTime.utc(2026, 10, 22, 2, 30),
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: episode)),
      )..debugSetLive(episode);

  Future<(LivePreviewController?, FakeLivePreviewEngine)> previewIn(_State state,
      {LivePreviewNotesEngine? notesEngine, int inFlightSeconds = 0, LivePreviewStart? noEngineStart}) async {
    final engine = FakeLivePreviewEngine();
    if (state == _State.cloud) return (null, engine);
    final preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      notesEngine: notesEngine,
    );
    switch (state) {
      case _State.starting:
        engine.startGate = Completer();
      case _State.noEngine:
        engine.nextStart = noEngineStart ?? const LivePreviewStart.none(LivePreviewReason.localeAssetMissing);
      default:
        break;
    }
    addTearDown(preview.dispose);
    preview.admit(language: 'en');
    await pumpEventQueue();
    if (state == _State.streaming ||
        state == _State.hybrid ||
        state == _State.notes ||
        state == _State.notesUnavailable) {
      engine.emit('a0', 'Okay, so the plan for Thursday is to ship the pendant update first.', true,
          startedAt: DateTime.utc(2026, 10, 27), endedAt: DateTime.utc(2026, 10, 27, 0, 0, 4));
      engine.emit('a1', 'Then we check the battery numbers with the team before the weekend.', true,
          startedAt: DateTime.utc(2026, 10, 27, 0, 0, 4), endedAt: DateTime.utc(2026, 10, 27, 0, 0, 9));
      if (state == _State.notes || state == _State.notesUnavailable) {
        engine.emit('a3', 'The beta goes out to the pilot cohort on Friday morning.', true);
      }
      engine.emit('a2', 'and if the overnight run looks clean we can', false,
          startedAt: DateTime.utc(2026, 10, 27, 0, 0, 9), endedAt: DateTime.utc(2026, 10, 27, 0, 0, 12));
      await pumpEventQueue();
    }
    return (preview, engine);
  }

  _Capture captureFor(_State state, LivePreviewController? preview, {int inFlightSeconds = 0}) {
    final capture = _Capture(preview: preview, admitted: state != _State.cloud, inFlightSeconds: inFlightSeconds);
    if (state == _State.cloud || state == _State.hybrid) {
      capture.segments = [
        TranscriptSegment(
            id: 'c1',
            text: 'Okay, so the plan for Thursday is to ship the pendant update first.',
            speaker: 'SPEAKER_0',
            isUser: true,
            personId: null,
            start: 0,
            end: 4,
            translations: []),
        TranscriptSegment(
            id: 'c2',
            text: 'Then we check the battery numbers with the team before the weekend.',
            speaker: 'SPEAKER_1',
            isUser: false,
            personId: null,
            start: 4,
            end: 9,
            translations: []),
      ];
    }
    return capture;
  }

  var android = false;

  Future<void> shoot(WidgetTester tester, String? file,
      {required bool light,
      required Widget home,
      required CaptureProvider capture,
      EpisodeProvider? episodes,
      double textScale = 1}) async {
    debugDefaultTargetPlatformOverride = android ? TargetPlatform.android : TargetPlatform.iOS;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final previous = OmiColors.active;
    OmiColors.active = light ? OmiPalette.light : OmiPalette.dark;
    addTearDown(() => OmiColors.active = previous);
    if (_evidence.isNotEmpty) await tester.runAsync(_loadFonts);
    final usage = UsageProvider();
    addTearDown(usage.dispose);
    const boundary = ValueKey('live_preview_evidence');
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ChangeNotifierProvider<DeviceProvider>.value(value: _Device()),
          ChangeNotifierProvider<ConnectivityProvider>.value(value: _Connectivity()),
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ChangeNotifierProvider<PhoneCallProvider>.value(value: _Call()),
          if (episodes != null) ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
          ChangeNotifierProvider(
              create: (_) => PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          locale: const Locale('en'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(brightness: light ? Brightness.light : Brightness.dark)
              .copyWith(platform: android ? TargetPlatform.android : TargetPlatform.iOS),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: DefaultTextStyle.merge(
              style: const TextStyle(fontFamily: 'SF Pro Display'),
              child: child!,
            ),
          ),
          home: home,
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.takeException(), isNull);
    final copy = tester.widgetList<Text>(find.byType(Text)).map((text) => text.data ?? '').join('\n');
    expect(copy.contains('...'), isFalse, reason: 'one-character ellipsis only');
    if (_evidence.isNotEmpty && file != null) {
      _paintProductFont(tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary)));
      await tester.pump();
      await tester.runAsync(() async {
        final render = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary));
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        final dir = await Directory(_evidence).create(recursive: true);
        await File('${dir.path}/$file').writeAsBytes(bytes!.buffer.asUint8List());
        image.dispose();
      });
    }
    debugDefaultTargetPlatformOverride = null;
  }

  final en = lookupAppLocalizations(const Locale('en'));
  // The PR's evidence set: iOS light, plus the on-device Summary in dark. Every other
  // platform/theme pass is a layout check only.
  const evidence = {
    'home-title-preview': 1,
    'home-before-title': 2,
    'home-no-preview': 3,
    'home-largest-type': 4,
    'summary-on-device-notes': 5,
    'summary-notes-unavailable': 6,
    'summary-server-notes': 7,
    'summary-on-device-notes-dark': 8,
    'transcript-mixed': 9,
    'transcript-no-engine': 10,
    'summary-largest-type': 11,
    'transcript-catching-up': 12,
    'home-unspaced-preview': 13,
    'summary-continues-hit-area': 14,
  };
  String? name(String slug, bool light) {
    if (android) return null;
    final number = evidence[light ? slug : '$slug-dark'];
    if (number == null) return null;
    return '${number.toString().padLeft(3, '0')}-mobile-ios-${light ? slug : '$slug-dark'}.png';
  }

  for (final (onAndroid, light) in [(false, false), (false, true), (true, false), (true, true)]) {
    final theme = '${onAndroid ? 'android' : 'ios'}, ${light ? 'light' : 'dark'}';

    testWidgets('streaming preview: provisional words secondary, settled words primary, no header ($theme)',
        (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.streaming)) ?? (null, null);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null, light: light, home: const LiveEpisodePage(), capture: capture);
      final volatile = tester.widget<Text>(find.text('and if the overnight run looks clean we can'));
      final settled = tester.widget<Text>(find.textContaining('Thursday'));
      expect(volatile.style?.color, OmiColors.textSecondary);
      expect(settled.style?.color, OmiColors.textPrimary);
      // The old "Live preview / On-device preview…" header is gone.
      expect(find.text('Live preview'), findsNothing);
      expect(find.text('On-device preview. The final transcript replaces it shortly.'), findsNothing);
      expect(capture.segments, isEmpty, reason: 'preview never enters capture segments');
    });

    testWidgets('engine starting ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.starting)) ?? (null, null);
      final capture = captureFor(_State.starting, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null, light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewStarting), findsOneWidget);
      expect(find.byType(OmiSpinner), findsOneWidget);
    });

    testWidgets('engine running, no words yet ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.listening)) ?? (null, null);
      final capture = captureFor(_State.listening, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null, light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewListening), findsOneWidget);
    });

    testWidgets('no on-device engine: Recording safely card, settings link only when it can land ($theme)',
        (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.noEngine)) ?? (null, null);
      final capture = captureFor(_State.noEngine, preview);
      addTearDown(capture.dispose);
      final episodes = episodesWith(episodeWith(title: ''));
      addTearDown(episodes.dispose);
      await shoot(tester, name('transcript-no-engine', light),
          light: light,
          home: const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
          capture: capture,
          episodes: episodes);
      expect(find.text(en.livePreviewNoEngineTitle), findsOneWidget);
      expect(find.text(en.livePreviewNoEngineBody), findsOneWidget);
      expect(find.byKey(const Key('live_preview_turn_on_live_text')), findsNothing,
          reason: 'locale_asset_missing has no settings deep-link');
      expect(find.byIcon(Icons.mic_none_rounded), findsOneWidget);
    });

    testWidgets('no engine with denied speech permission offers Turn on live text ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.noEngine,
              noEngineStart: const LivePreviewStart.none(LivePreviewReason.speechPermissionDenied))) ??
          (null, null);
      final capture = captureFor(_State.noEngine, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null, light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewNoEngineTitle), findsOneWidget);
      expect(find.text(en.livePreviewTurnOnLiveText), findsOneWidget);
      expect(tester.getSize(find.byKey(const Key('live_preview_turn_on_live_text'))).height,
          greaterThanOrEqualTo(kOmiMinTapTarget));
    });

    for (final onEpisodePage in [false, true]) {
      testWidgets(
          'hybrid: final segments, the Live-on-this-phone divider, then uncovered preview lines '
          '(${onEpisodePage ? 'episode page' : 'capture page'}, $theme)', (tester) async {
        android = onAndroid;
        final (preview, _) = await tester.runAsync(() => previewIn(_State.hybrid)) ?? (null, null);
        final capture = captureFor(_State.hybrid, preview, inFlightSeconds: 22);
        capture.applyInProgressConversation(ServerConversation(
            id: 'c1',
            createdAt: DateTime.utc(2026, 10, 27),
            structured: Structured('', ''),
            transcriptSegments: capture.segments.reversed.toList()));
        expect(capture.segments.map((s) => s.start), [0, 4]);
        addTearDown(capture.dispose);
        final episodes = onEpisodePage ? episodesWith(episodeWith()) : null;
        if (episodes != null) addTearDown(episodes.dispose);
        await shoot(tester, onEpisodePage ? name('transcript-mixed', light) : null,
            light: light,
            home: const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
            capture: capture,
            episodes: episodes);
        // Finals with their speakers come first.
        expect(find.textContaining('Thursday', findRichText: true), findsWidgets);
        // The divider names where the preview continues.
        expect(find.byKey(const Key('live_preview_divider')), findsOneWidget);
        expect(find.text(en.livePreviewOnPhoneDivider), findsOneWidget);
        // Lines the finals already cover do not repeat under the divider.
        expect(find.byKey(const Key('live_preview_tail_a0')), findsNothing);
        expect(find.byKey(const Key('live_preview_tail_a1')), findsNothing);
        // The uncovered volatile tail does, lighter than settled text.
        final tail = tester.widget<Text>(
            find.descendant(of: find.byKey(const Key('live_preview_tail_a2')), matching: find.byType(Text)));
        expect(tail.style?.color, OmiColors.textSecondary);
        // One quiet behind-line instead of the uploading pill and chunk count; on the episode
        // page it is the last line under the transcript.
        final behind = find.byKey(const Key('live_preview_behind_line'));
        expect(behind, findsOneWidget);
        expect(find.text(en.livePreviewBehind(en.timeCompactSecs(20))), findsOneWidget);
        expect(find.text(en.uploadingAudioForTranscription(en.timeCompactSecs(22))), findsNothing);
        expect(find.text(en.captureChunksPending(2)), findsNothing);
        if (onEpisodePage) {
          expect(tester.getTopLeft(behind).dy,
              greaterThan(tester.getBottomLeft(find.byKey(const Key('live_preview_divider'))).dy));
        }
      });
    }

    testWidgets('catching-up follows preview arrivals without waiting for a capture notification ($theme)',
        (tester) async {
      android = onAndroid;
      final (preview, engine) = await tester.runAsync(() => previewIn(_State.listening)) ?? (null, null);
      final capture = captureFor(_State.listening, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null,
          light: light, home: const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript), capture: capture);
      expect(find.text(en.livePreviewCatchingUp), findsNothing);
      engine!.emit('new', 'Words still waiting for the final transcript', true);
      await tester.pump();
      expect(find.text(en.livePreviewCatchingUp), findsOneWidget);
      preview!.endCapture();
      await tester.pump();
      expect(find.text(en.livePreviewCatchingUp), findsNothing);
    });

    for (final seconds in [0, 3, 22]) {
      testWidgets('preview ahead with $seconds pending seconds ($theme)', (tester) async {
        android = onAndroid;
        final (preview, _) = await tester.runAsync(() => previewIn(_State.hybrid)) ?? (null, null);
        final capture = captureFor(_State.hybrid, preview, inFlightSeconds: seconds);
        addTearDown(capture.dispose);
        await shoot(tester, seconds == 0 ? name('transcript-catching-up', light) : null,
            light: light, home: const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript), capture: capture);
        expect(find.byKey(const Key('live_preview_tail_a2')), findsOneWidget);
        if (seconds == 0) {
          expect(find.text(en.livePreviewCatchingUp), findsOneWidget,
              reason: 'uploaded audio can still be awaiting the final transcript');
        } else if (seconds <= 5) {
          expect(find.byKey(const Key('live_preview_behind_line')), findsNothing,
              reason: 'a known small lag keeps the existing quiet threshold');
        } else {
          expect(find.text(en.livePreviewBehind(en.timeCompactSecs(20))), findsOneWidget);
        }
      });
    }

    for (final hasWords in [false, true]) {
      testWidgets('no catching-up line when ${hasWords ? 'finals cover the preview' : 'no preview words yet'} ($theme)',
          (tester) async {
        android = onAndroid;
        final state = hasWords ? _State.hybrid : _State.listening;
        final (preview, _) = await tester.runAsync(() => previewIn(state)) ?? (null, null);
        final capture = captureFor(state, preview);
        addTearDown(capture.dispose);
        if (hasWords) {
          capture.segments = [
            TranscriptSegment(
                id: 'all',
                text: 'Final transcript',
                speaker: 'SPEAKER_0',
                isUser: true,
                personId: null,
                start: 0,
                end: 12,
                translations: []),
          ];
        }
        await shoot(tester, null,
            light: light, home: const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript), capture: capture);
        expect(find.byKey(const Key('live_preview_behind_line')), findsNothing);
      });
    }

    testWidgets('not admitted: today\'s cloud transcript, unchanged ($theme)', (tester) async {
      android = onAndroid;
      final capture = captureFor(_State.cloud, null);
      addTearDown(capture.dispose);
      await shoot(tester, null, light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.textContaining('Thursday', findRichText: true), findsWidgets);
      expect(find.byKey(const Key('live_preview_divider')), findsNothing);
    });

    for (final largest in [false, true]) {
      testWidgets(
          'summary: So far drafts on this phone, Live card without a speaker label'
          '${largest ? ', largest text' : ''} ($theme)', (tester) async {
        android = onAndroid;
        final (preview, _) = await tester.runAsync(() => previewIn(_State.notes, notesEngine: (text, language) async {
                  return ['Ship the pendant update first', 'Check battery numbers before the weekend'];
                })) ??
            (null, null);
        final capture = captureFor(_State.notes, preview);
        addTearDown(capture.dispose);
        final episodes = episodesWith(episodeWith());
        addTearDown(episodes.dispose);
        await shoot(tester, name(largest ? 'summary-largest-type' : 'summary-on-device-notes', light),
            light: light,
            home: const LiveEpisodePage(),
            capture: capture,
            episodes: episodes,
            textScale: largest ? _largestTextScale : 1);
        // On-device bullets with their provenance tag and footnote.
        expect(find.byKey(const Key('episode_on_device_notes')), findsOneWidget);
        expect(find.text('Ship the pendant update first'), findsOneWidget);
        expect(find.text(en.episodeOnThisPhone), findsOneWidget);
        expect(find.text(en.episodeOnDeviceNotesFootnote), findsOneWidget);
        // No server notes exist, so the "aren't updating" line is gone.
        expect(find.byKey(const Key('episode_notes_unavailable')), findsNothing);
        expect(find.text(en.episodeNotesStartWithTranscript), findsNothing);
        // One calm header line: the length, then "· since …"; no moment count, no wrap.
        expect(find.byKey(const Key('live_episode_status')), findsOneWidget);
        final meta = tester.widget<Text>(find.byKey(const Key('live_episode_meta')));
        expect(meta.data, startsWith(en.episodeLiveSince('').trim()));
        expect(meta.maxLines, 1);
        // The pinned header is opaque in the page's colour.
        final header = tester.widget<ColoredBox>(find.byKey(const Key('live_episode_pinned_header')));
        expect(header.color, OmiColors.surface0);
        if (largest) return;
        // The Live card: preview text, no "You" label, and the Open transcript link; the old
        // "Live Transcript" card with speaker labels is gone.
        expect(find.byKey(const Key('live_episode_preview_card')), findsOneWidget);
        expect(find.text(en.liveCardTitle), findsOneWidget);
        expect(find.text(en.episodeOpenTranscript), findsOneWidget);
        expect(find.text(en.liveTranscript), findsNothing);
        expect(tester.getSize(find.byKey(const Key('live_episode_open_transcript'))).height,
            greaterThanOrEqualTo(kOmiMinTapTarget));
        final richTexts = tester.widgetList<Text>(
            find.descendant(of: find.byKey(const Key('live_episode_preview_card')), matching: find.byType(Text)));
        expect(richTexts.any((text) => (text.data ?? '').startsWith('You')), isFalse,
            reason: 'preview text has no speaker attribution');
        // The newest words stay visible: the card trims at the start, never the end.
        final card = tester.widget<RichText>(find
            .descendant(of: find.byKey(const Key('live_episode_preview_card_text')), matching: find.byType(RichText))
            .first);
        expect(card.text.toPlainText(), endsWith('and if the overnight run looks clean we can'));
      });
    }

    testWidgets('summary with server running notes: at most four, the newest; drafts hidden ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.notes, notesEngine: (text, language) async {
                return ['Drafted on the phone'];
              })) ??
          (null, null);
      final capture = captureFor(_State.notes, preview);
      addTearDown(capture.dispose);
      const bullets = [
        'Pendant update ships before the app release',
        'Battery numbers reviewed with the hardware team',
        'Overnight soak run decides the beta date',
        'Pilot cohort gets the beta on Friday morning',
        'Support macros updated for the new pairing flow',
        'Follow up on the charging case supplier quote',
      ];
      final episodes = episodesWith(episodeWith(bullets: bullets));
      addTearDown(episodes.dispose);
      await shoot(tester, name('summary-server-notes', light),
          light: light, home: const LiveEpisodePage(), capture: capture, episodes: episodes);
      for (final bullet in bullets.take(2)) {
        expect(find.text(bullet), findsNothing);
      }
      for (final bullet in bullets.skip(2)) {
        expect(find.text(bullet), findsOneWidget);
      }
      expect(find.byKey(const Key('episode_on_device_notes')), findsNothing);
      expect(find.byKey(const Key('episode_notes_unavailable')), findsNothing);
      expect(find.text(en.episodeOnThisPhone), findsNothing);
    });

    testWidgets('summary with no engine on the phone: the quiet line ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester
              .runAsync(() => previewIn(_State.notesUnavailable, notesEngine: (text, language) async => null)) ??
          (null, null);
      final capture = captureFor(_State.notesUnavailable, preview);
      addTearDown(capture.dispose);
      final episodes = episodesWith(episodeWith());
      addTearDown(episodes.dispose);
      await shoot(tester, name('summary-notes-unavailable', light),
          light: light, home: const LiveEpisodePage(), capture: capture, episodes: episodes);
      expect(find.text(en.episodeNotesStartWithTranscript), findsOneWidget);
      expect(find.text(en.episodeOnThisPhone), findsNothing, reason: 'no bullets, no provenance tag');
      expect(find.byKey(const Key('episode_on_device_notes')), findsNothing);
      expect(find.byKey(const Key('episode_notes_unavailable')), findsNothing);
    });

    Widget homeRow() => Builder(
          builder: (context) => Scaffold(
            backgroundColor: OmiColors.surface0,
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
                child: ListView(children: const [LiveEpisodeRow()]),
              ),
            ),
          ),
        );

    for (final (slug, title, state, textScale) in [
      ('home-title-preview', 'Meeting Prep', _State.streaming, 1.0),
      ('home-before-title', '', _State.streaming, 1.0),
      ('home-no-preview', 'Meeting Prep', _State.listening, 1.0),
      ('home-largest-type', 'Meeting Prep', _State.streaming, _largestTextScale),
    ]) {
      testWidgets('home live row: $slug ($theme)', (tester) async {
        android = onAndroid;
        final (preview, _) = await tester.runAsync(() => previewIn(state)) ?? (null, null);
        final capture = captureFor(state, preview);
        addTearDown(capture.dispose);
        final episodes = episodesWith(episodeWith(title: title), now: DateTime.utc(2026, 10, 22, 2, 26, 24));
        addTearDown(episodes.dispose);
        await shoot(tester, name(slug, light),
            light: light, home: homeRow(), capture: capture, episodes: episodes, textScale: textScale);
        expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
        // The tile carries the same session length the page counts, in whole minutes.
        expect(find.text('8m'), findsOneWidget);
        expect(find.text(title.isEmpty ? en.episodeListeningNow : title), findsOneWidget);
        if (state == _State.streaming) {
          // Line two is the preview, trimmed at the start so the newest words stay.
          final line = tester.widget<Text>(
              find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
          final words = line.textSpan!.toPlainText();
          expect(words, endsWith('we can'));
          expect(words.startsWith('…') || words.startsWith('Okay'), isTrue,
              reason: 'trimmed at the start, never the end');
        } else {
          // No preview text: today's subtitle without the duration.
          expect(find.byKey(const Key('home_live_episode_preview')), findsNothing);
          expect(find.text(en.live), findsOneWidget);
        }
        // The row keeps its size: the tile never outgrows it.
        if (textScale == 1) {
          expect(tester.getSize(find.byKey(const Key('home_live_episode_row'))).height, lessThan(80));
        }
      });
    }

    testWidgets('home unspaced preview keeps the newest graphemes ($theme)', (tester) async {
      android = onAndroid;
      final (preview, engine) = await tester.runAsync(() => previewIn(_State.listening)) ?? (null, null);
      const newest = '明日の予定を確認しましょう';
      engine!.emit('latest', '${List.filled(40, '今日の会議で話し合った内容').join()}$newest', true);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      final episodes = episodesWith(episodeWith());
      addTearDown(episodes.dispose);
      await shoot(tester, name('home-unspaced-preview', light),
          light: light, home: homeRow(), capture: capture, episodes: episodes);
      final text = tester.widget<Text>(
          find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
      expect(text.textSpan!.toPlainText(), startsWith('…'));
      expect(text.textSpan!.toPlainText(), endsWith(newest));
    });

    testWidgets('Continues pill keeps its compact visual inside the larger hit area ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.streaming)) ?? (null, null);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      final episodes = EpisodeProvider(
        clock: () => t0.add(const Duration(minutes: 12)),
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: episodeWith())),
        lookup: (_) async => ApiSuccess(
            EpisodeRead(enabled: true, episode: episodeWith(title: 'Earlier plans', id: 'old').copyWith(live: false))),
      )..debugSetLive(episodeWith());
      addTearDown(episodes.dispose);
      await episodes.recoverPrevious('old');
      await shoot(tester, name('summary-continues-hit-area', light),
          light: light, home: const LiveEpisodePage(), capture: capture, episodes: episodes);
      expect(find.text('Continues “Earlier plans”'), findsOneWidget);
    });

    testWidgets('home capture card shows the newest preview line in its last-line slot ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.streaming)) ?? (null, null);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      await shoot(tester, null,
          light: light,
          // Read the palette at build time, after shoot() selects light or dark.
          home: Builder(
            builder: (context) => Scaffold(
              backgroundColor: OmiColors.surface0,
              body: const SafeArea(
                child: Padding(
                  padding: EdgeInsets.all(OmiSpacing.md),
                  child: Align(alignment: Alignment.topCenter, child: ConversationCaptureWidget(showsCall: true)),
                ),
              ),
            ),
          ),
          capture: capture);
      expect(find.textContaining('and if the overnight run looks clean we can', findRichText: true), findsOneWidget);
    });
  }
}

Future<void> _loadFonts() async {
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
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'FlutterTest',
    'SF Pro Display',
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
  // Evidence only: SF Pro lacks CJK glyphs. Use the host's CJK face without
  // adding a licensed system font to the app bundle or repository.
  final cjk = File('/System/Library/Fonts/Hiragino Sans GB.ttc');
  if (cjk.existsSync()) {
    await (FontLoader('PreviewCjkEvidence')..addFont(Future.value(ByteData.sublistView(await cjk.readAsBytes()))))
        .load();
  }
  final icons = _materialIcons();
  if (icons != null) {
    final bytes = await icons.readAsBytes();
    await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))))).load();
  }
}

/// Repaints every paragraph in the SF Pro fixture, so text styled with a family
/// the test engine lacks does not render as boxes in the evidence.
void _paintProductFont(RenderObject object) {
  if (object is RenderParagraph) object.text = _productFont(object.text);
  object.visitChildren(_paintProductFont);
  object.markNeedsPaint();
}

InlineSpan _productFont(InlineSpan span) {
  if (span is! TextSpan) return span;
  final style = span.style ?? const TextStyle();
  final family = style.fontFamily;
  if (family != null && (family.startsWith('packages/') || family.contains('Icons'))) return span;
  return TextSpan(
    text: span.text,
    style: style.copyWith(fontFamily: 'SF Pro Display', fontFamilyFallback: const ['PreviewCjkEvidence']),
    children: span.children?.map(_productFont).toList(),
    recognizer: span.recognizer,
    semanticsLabel: span.semanticsLabel,
    locale: span.locale,
  );
}

File? _materialIcons() {
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++) {
    for (final path in ['artifacts/material_fonts', 'material_fonts']) {
      final candidate = File('${dir.path}/$path/MaterialIcons-Regular.otf');
      if (candidate.existsSync()) return candidate;
    }
    if (dir.path == dir.parent.path) break;
    dir = dir.parent;
  }
  return null;
}
