// Home while this phone records (David, 2026-11-16): tapping record keeps the reader on Home, and
// the bottom row becomes the recording bar. Undo for the first five seconds, then Wrap Up.
//
// Renders the real HomePage. With HOME_RECORDING_BAR_RENDER_OUTPUT set it writes iPhone-sized PNGs
// for the PR's UI evidence; in CI it is a layout and overflow check that writes nothing.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/home/widgets/home_recording_bar.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/app_globals.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';
import '../helpers/sfpro_font_fixtures.dart';

const _output = String.fromEnvironment('HOME_RECORDING_BAR_RENDER_OUTPUT');
final _boundary = GlobalKey();

/// The phone recording, as Home reads it. Nothing reaches the mic, the socket or the server.
class _PhoneCapture extends CaptureProvider {
  _PhoneCapture() : super(localSegmentStore: LocalSegmentStore.disabled());

  bool phoneLive = false;
  DateTime? startedAt;
  int discards = 0;
  int finishes = 0;

  void startPhone(Duration ago, {List<TranscriptSegment> lines = const []}) {
    phoneLive = true;
    startedAt = DateTime.now().subtract(ago);
    recordingState = RecordingState.record;
    segments = List.of(lines);
    notifyListeners();
  }

  @override
  String? get liveCaptureSource => phoneLive ? 'phone' : null;

  @override
  DateTime? get liveCaptureStartedAt => phoneLive ? startedAt : null;

  @override
  bool get isPhoneMicBatchRecording => false;

  @override
  bool get isPhoneMicPaused => false;

  @override
  Future<bool> discardPhoneRecording() async {
    discards++;
    phoneLive = false;
    recordingState = RecordingState.stop;
    segments = [];
    notifyListeners();
    return true;
  }

  @override
  Future<void> finishCapture() async {
    finishes++;
    phoneLive = false;
    recordingState = RecordingState.stop;
    notifyListeners();
  }
}

final _today = DateTime.now();

ServerConversation _conversation(String id, String title, String emoji, Duration ago, Duration length) {
  final started = _today.subtract(ago);
  return ServerConversation(
    id: id,
    speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
    createdAt: started,
    startedAt: started,
    finishedAt: started.add(length),
    structured: Structured(title, '$title overview.', emoji: emoji, category: 'work'),
    transcriptSegments: [],
  );
}

ConversationProvider _history() => ConversationProvider(isSignedIn: () => false)
  ..conversations = [
    _conversation('c1', 'Call from the printer', '🖨️', const Duration(hours: 1), const Duration(minutes: 25)),
    _conversation('c2', 'Call with the venue', '📞', const Duration(hours: 2), const Duration(minutes: 25)),
    _conversation('c3', 'Hiring plan', '🧭', const Duration(hours: 3), const Duration(minutes: 40)),
    _conversation('c4', 'Standup', '☕', const Duration(hours: 5), const Duration(minutes: 15)),
  ]
  ..groupConversationsByDate();

TranscriptSegment _line(String text) => TranscriptSegment(
      id: 'seg-${text.hashCode}',
      text: text,
      speaker: 'SPEAKER_1',
      isUser: false,
      personId: null,
      translations: [],
      start: 0,
      end: 4,
    );

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
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto',
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

/// On a phone, text with no family uses the system font; the test engine draws it with a placeholder
/// face. The evidence theme names SF Pro where a theme style carries it (the app bar, the toast).
/// Text whose own style replaces the inherited one with no family (Home's tab titles) still draws
/// as placeholder boxes here, and only here.
ThemeData _evidenceTheme(Brightness brightness) {
  final theme = buildOmiTheme(brightness: brightness);
  return theme.copyWith(
    textTheme: theme.textTheme.apply(fontFamily: 'SF Pro Display'),
    snackBarTheme: theme.snackBarTheme.copyWith(
      contentTextStyle: theme.snackBarTheme.contentTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
    appBarTheme: theme.appBarTheme.copyWith(
      titleTextStyle: (theme.appBarTheme.titleTextStyle ?? const TextStyle()).copyWith(fontFamily: 'SF Pro Display'),
      toolbarTextStyle:
          (theme.appBarTheme.toolbarTextStyle ?? const TextStyle()).copyWith(fontFamily: 'SF Pro Display'),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadFonts);

  Future<_PhoneCapture> pumpHome(WidgetTester tester, Brightness brightness) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    tester.view.padding = const FakeViewPadding(top: 59, bottom: 34);
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(brightness);
    _stubPlugins();
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: 'fake',
          appId: '1:1:ios:fake',
          messagingSenderId: '1',
          projectId: 'demo-omi-local',
        ),
      );
    }
    await tester.runAsync(() async {
      await JourneyHermeticBoot.start(
        extraPrefs: {'onboardingCompleted': true, 'permissionsCompleted': true, 'aiConsentGiven': true},
      );
      try {
        await ServiceManager.init();
      } catch (_) {}
    });
    addTearDown(JourneyHermeticBoot.stop);

    final capture = _PhoneCapture();
    await JourneyHermeticBoot.pumpPage(
      tester,
      page: const HomePage(),
      providers: _homeProviders(capture),
      appBuilder: (page) => RepaintBoundary(
        key: _boundary,
        child: MaterialApp(
          navigatorKey: globalNavigatorKey,
          debugShowCheckedModeBanner: false,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          theme: _evidenceTheme(brightness),
          home: page,
        ),
      ),
    );
    await settle(tester);
    return capture;
  }

  Future<void> capture(WidgetTester tester, String file) async {
    expect(tester.takeException(), isNull);
    if (_output.isEmpty) return;
    await tester.runAsync(() async {
      final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(_output).create(recursive: true);
      await File('$_output/$file').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  for (final (brightness, mode, base) in [(Brightness.light, 'light', 1), (Brightness.dark, 'dark', 5)]) {
    testWidgets('$mode: Home before, at the start (Undo), recording (Wrap Up) and after Undo', (tester) async {
      final phone = await pumpHome(tester, brightness);
      expect(find.byType(HomeRecordingBar), findsNothing);
      expect(find.byKey(const ValueKey('home_ask_omi_bar')), findsOneWidget);
      await capture(tester, '${_n(base)}-mobile-ios-home-idle-$mode.png');

      // The tap: Home stays, and the bottom row is the recording bar with Undo.
      phone.startPhone(const Duration(seconds: 3));
      await settle(tester);
      expect(find.byType(HomeRecordingBar), findsOneWidget);
      expect(find.byKey(const ValueKey('home_ask_omi_bar')), findsNothing);
      expect(find.byKey(const ValueKey('home_recording_bar_undo')), findsOneWidget);
      expect(find.text('Recording with your phone'), findsOneWidget);
      await capture(tester, '${_n(base + 1)}-mobile-ios-recording-bar-undo-$mode.png');

      // Four minutes in: Wrap Up.
      phone.startPhone(const Duration(minutes: 4, seconds: 12), lines: [
        _line('Then I need the deposit by Friday, and a walkthrough with your AV person.'),
      ]);
      await settle(tester);
      expect(find.byKey(const ValueKey('home_recording_bar_undo')), findsNothing);
      expect(find.byKey(const ValueKey('home_recording_bar_wrap_up')), findsOneWidget);
      await capture(tester, '${_n(base + 2)}-mobile-ios-recording-bar-wrap-up-$mode.png');

      // Undo discards: the bar goes, the chat bar and the round button return, and a toast says so.
      phone.startPhone(const Duration(seconds: 2));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('home_recording_bar_undo')));
      await settle(tester);
      expect(phone.discards, 1);
      expect(phone.finishes, 0);
      expect(find.byType(HomeRecordingBar), findsNothing);
      expect(find.text('Recording discarded'), findsOneWidget);
      await capture(tester, '${_n(base + 3)}-mobile-ios-recording-discarded-$mode.png');

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 5));
      debugDefaultTargetPlatformOverride = null;
    });
  }
}

String _n(int i) => i.toString().padLeft(3, '0');

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

List<SingleChildWidget> _homeProviders(_PhoneCapture capture) {
  return [
    ChangeNotifierProvider<ConversationProvider>(create: (_) => _history()),
    ChangeNotifierProvider(create: (_) => AuthenticationProvider(initializeListeners: false)),
    ChangeNotifierProvider<CaptureProvider>.value(value: capture),
    ChangeNotifierProvider(create: (_) => LocalRecordingsProvider(initialize: false)),
    ChangeNotifierProvider(
      create: (_) => DeviceProvider(
        bleDiagnosticsLoader: (_) async => throw StateError('fixture: BLE diagnostics unused'),
        findDeviceRunner: (_) async => false,
      ),
    ),
    ChangeNotifierProvider(create: (_) => AnnouncementProvider()),
    ChangeNotifierProvider(create: (_) => ActionItemsProvider()),
    ChangeNotifierProvider(create: (_) => SyncProvider(startBackgroundSync: false)),
    ChangeNotifierProvider(create: (_) => TaskIntegrationProvider()),
    ChangeNotifierProvider(create: (_) => PhoneCallProvider.forTesting()),
    ChangeNotifierProvider(create: (_) => GoalsProvider()),
    ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
      create: (_) => AddAppProvider(),
      update: (_, app, previous) => (previous?..setAppProvider(app)) ?? (AddAppProvider()..setAppProvider(app)),
    ),
    ChangeNotifierProvider(
      create: (_) =>
          UserProvider(privateCloudSyncFetcher: () async => false, privateCloudSyncSetter: (_) async => true),
    ),
    ChangeNotifierProvider(create: (_) => MemoriesProvider()),
    ChangeNotifierProvider(create: (_) => PeopleProvider()),
    ChangeNotifierProvider(create: (_) => LocaleProvider()),
    ChangeNotifierProvider(
      create: (_) => SpeakerTagPromptsProvider(
        fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
      ),
    ),
  ];
}

void _stubPlugins() {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const channels = [
    'flutter_foreground_task/methods',
    'flutter.baseflow.com/geolocator',
    'flutter.baseflow.com/permissions/methods',
    'dev.fluttercommunity.plus/connectivity',
    'dev.fluttercommunity.plus/connectivity_status',
    'xyz.luan/audioplayers',
    'plugins.flutter.io/path_provider',
    'plugins.flutter.io/shared_preferences',
    'plugins.flutter.io/firebase_messaging',
    'com.omi/phone_calls',
    'com.omi/phone_calls/events',
  ];
  for (final name in channels) {
    messenger.setMockMethodCallHandler(MethodChannel(name), (call) async {
      switch (call.method) {
        case 'check':
          return ['wifi'];
        case 'checkPermission':
        case 'checkServiceStatus':
          return 1;
        case 'getAll':
          return <String, Object>{};
        case 'getApplicationDocumentsDirectory':
        case 'getTemporaryDirectory':
        case 'getApplicationSupportDirectory':
          return '/tmp/omi-home-recording-bar';
        default:
          return null;
      }
    });
  }
  messenger.setMockStreamHandler(
    const EventChannel('com.omi/phone_calls/events'),
    MockStreamHandler.inline(onListen: (args, sink) {}, onCancel: (args) {}),
  );
}
