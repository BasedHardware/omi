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

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../support/live_preview_fakes.dart';

/// Every state of the local-preview live transcript surface, iOS look, light and dark.
/// `--dart-define=OMI_LIVE_PREVIEW_EVIDENCE_DIR=<dir>` writes the PNGs; without it this is a
/// layout/overflow/copy check only.
const _evidence = String.fromEnvironment('OMI_LIVE_PREVIEW_EVIDENCE_DIR');

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
  int getInFlightSeconds() => 0;
  List<dynamic> getSessionUnsyncedWals(int start) => const [];
  List<dynamic> getSessionWals(int start) => const [];
}

class _Syncs {
  final phone = _PhoneSync();
}

class _Wal implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// A real CaptureProvider recording from the pendant, with the admission and
/// the preview model injected (the socket path is covered by the routing tests).
class _Capture extends CaptureProvider {
  _Capture({this.preview, this.admitted = false})
      : super(
          walService: _Wal(),
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

enum _State { streaming, starting, listening, transcribing, cloud }

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<(LivePreviewController?, FakeLivePreviewEngine)> previewIn(_State state) async {
    final engine = FakeLivePreviewEngine();
    if (state == _State.cloud) return (null, engine);
    final preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
    );
    switch (state) {
      case _State.starting:
        engine.startGate = Completer();
      case _State.transcribing:
        engine.nextStart = const LivePreviewStart.none(LivePreviewReason.localeAssetMissing);
      default:
        break;
    }
    preview.admit(language: 'en');
    await pumpEventQueue();
    if (state == _State.streaming) {
      engine.emit('a0', 'Okay, so the plan for Thursday is to ship the pendant update first.', true);
      engine.emit('a1', 'Then we check the battery numbers with the team before the weekend.', true);
      engine.emit('a2', 'and if the overnight run looks clean we can', false);
      await pumpEventQueue();
    }
    return (preview, engine);
  }

  _Capture captureFor(_State state, LivePreviewController? preview) {
    final capture = _Capture(preview: preview, admitted: state != _State.cloud);
    if (state == _State.cloud) {
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

  Future<void> shoot(WidgetTester tester, String file,
      {required bool light, required Widget home, required CaptureProvider capture}) async {
    debugDefaultTargetPlatformOverride = android ? TargetPlatform.android : TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
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
          builder: (context, child) => DefaultTextStyle.merge(
            style: const TextStyle(fontFamily: 'SF Pro Display'),
            child: child!,
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
    if (_evidence.isNotEmpty) {
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
  var index = 0;
  String name(String slug, bool light) => '${(++index).toString().padLeft(3, '0')}-mobile-'
      '${android ? 'android' : 'ios'}-$slug-${light ? 'light' : 'dark'}.png';

  for (final (onAndroid, light) in [(false, false), (false, true), (true, false), (true, true)]) {
    final theme = '${onAndroid ? 'android' : 'ios'}, ${light ? 'light' : 'dark'}';

    testWidgets('streaming preview: provisional words secondary, settled words primary ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.streaming)) ?? (null, null);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      await shoot(tester, name('live-preview-streaming', light),
          light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewLabel), findsOneWidget);
      expect(find.text(en.livePreviewExplanation), findsOneWidget);
      final volatile = tester.widget<Text>(find.text('and if the overnight run looks clean we can'));
      final settled = tester.widget<Text>(find.textContaining('Thursday'));
      expect(volatile.style?.color, OmiColors.textSecondary);
      expect(settled.style?.color, OmiColors.textPrimary);
      expect(capture.segments, isEmpty, reason: 'preview never enters capture segments');
    });

    testWidgets('engine starting ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.starting)) ?? (null, null);
      final capture = captureFor(_State.starting, preview);
      addTearDown(capture.dispose);
      await shoot(tester, name('live-preview-starting', light),
          light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewStarting), findsOneWidget);
      expect(find.byType(OmiSpinner), findsOneWidget);
    });

    testWidgets('engine running, no words yet ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.listening)) ?? (null, null);
      final capture = captureFor(_State.listening, preview);
      addTearDown(capture.dispose);
      await shoot(tester, name('live-preview-listening', light),
          light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewListening), findsOneWidget);
      expect(find.text(en.livePreviewLabel), findsOneWidget);
    });

    testWidgets('no on-device engine: calm Transcribing, no error, no setup action ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.transcribing)) ?? (null, null);
      final capture = captureFor(_State.transcribing, preview);
      addTearDown(capture.dispose);
      await shoot(tester, name('live-preview-no-engine', light),
          light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewTranscribingTitle), findsOneWidget);
      expect(find.text(en.livePreviewTranscribingMessage), findsOneWidget);
      expect(find.descendant(of: find.byKey(const Key('live_preview_transcribing')), matching: find.byType(OmiButton)),
          findsNothing);
      expect(find.text(en.livePreviewLabel), findsNothing);
    });

    testWidgets('not admitted: today\'s cloud transcript, unchanged ($theme)', (tester) async {
      android = onAndroid;
      final capture = captureFor(_State.cloud, null);
      addTearDown(capture.dispose);
      await shoot(tester, name('cloud-transcript-unchanged', light),
          light: light, home: const LiveEpisodePage(), capture: capture);
      expect(find.text(en.livePreviewLabel), findsNothing);
      expect(find.textContaining('Thursday', findRichText: true), findsWidgets);
    });

    testWidgets('home capture card shows the newest preview line in its last-line slot ($theme)', (tester) async {
      android = onAndroid;
      final (preview, _) = await tester.runAsync(() => previewIn(_State.streaming)) ?? (null, null);
      final capture = captureFor(_State.streaming, preview);
      addTearDown(capture.dispose);
      await shoot(tester, name('home-card-preview-line', light),
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
    style: style.copyWith(fontFamily: 'SF Pro Display'),
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
