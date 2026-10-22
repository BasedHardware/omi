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
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Renders the chat while Omi answers a message with a video attached: the bubble shows the
/// clip's poster frame with a play badge and length, and the empty composer offers Stop.
/// With `--dart-define=CHAT_ERGONOMICS_RENDER_OUTPUT=<dir>` it writes the PR evidence PNG.
final _boundary = GlobalKey();

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
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(rootBundle.load('assets/fonts/SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  // The prompt preview asks for `monospace`, then Menlo, which iOS provides. Use a local monospace
  // face for the evidence when the machine has one; the layout assertions do not depend on it.
  const courier = '/System/Library/Fonts/Supplemental/Courier New.ttf';
  if (File(courier).existsSync()) {
    for (final family in ['monospace', 'Menlo']) {
      final mono = FontLoader(family)..addFont(Future.value(ByteData.sublistView(File(courier).readAsBytesSync())));
      await mono.load();
    }
  }
}

/// A synthetic poster frame: a sky over a road, drawn in the test (no user media).
Future<File> _posterFrame() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(const Rect.fromLTWH(0, 0, 384, 216), Paint()..color = const Color(0xFF6FA8DC));
  canvas.drawRect(const Rect.fromLTWH(0, 130, 384, 86), Paint()..color = const Color(0xFF555B66));
  canvas.drawRect(const Rect.fromLTWH(60, 40, 264, 30), Paint()..color = const Color(0xFF1F3A93));
  canvas.drawRect(const Rect.fromLTWH(60, 70, 14, 70), Paint()..color = const Color(0xFF1F3A93));
  canvas.drawRect(const Rect.fromLTWH(310, 70, 14, 70), Paint()..color = const Color(0xFF1F3A93));
  final image = await recorder.endRecording().toImage(384, 216);
  final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
  final file = File('${Directory.systemTemp.createTempSync('omi-poster').path}/poster.png');
  await file.writeAsBytes(bytes!.buffer.asUint8List());
  return file;
}

class _OlderSessions extends ChatSessionsApi {
  _OlderSessions(this.older);

  final List<ServerMessage> older;

  @override
  Future<ApiResult<List<ServerMessage>>> messages(String id, {int offset = 0, int limit = 100}) async =>
      ApiSuccess(older);

  @override
  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) async => const ApiSuccess('Title');
}

class _QuietMessages extends MessageProvider {
  _QuietMessages(ChatSessionsApi sessions) : super(sessionsApi: sessions);

  @override
  Future<void> fetchChatApps() async {}

  @override
  Future refreshMessages({bool dropdownSelected = false}) async {}
}

Widget _chat(MessageProvider provider) => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      builder: (context, child) =>
          MediaQuery(data: MediaQuery.of(context).copyWith(disableAnimations: true), child: child!),
      home: MultiProvider(
        providers: [
          ChangeNotifierProvider<MessageProvider>.value(value: provider),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (_) => HomeProvider()),
          ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
          ChangeNotifierProvider(create: (_) => AppProvider()),
          ChangeNotifierProvider(
            create: (_) => IntegrationProvider(
              fetchStatus: (_) async => null,
              saveStatus: (_, __) async => false,
              deleteStatus: (_) async => false,
              persistPref: (_, __) async {},
            ),
          ),
        ],
        child: RepaintBoundary(key: _boundary, child: const ChatPage()),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const output = String.fromEnvironment('CHAT_ERGONOMICS_RENDER_OUTPUT');

  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });

  setUp(() async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('a video message shows its poster, and Stop is offered while Omi answers', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);

    final poster = (await tester.runAsync(_posterFrame))!;
    final thinking = Completer<void>();
    final provider = _QuietMessages(_OlderSessions(const []))
      ..chatSessionId = 'session-1'
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r1', 'Looking at the video', MessageChunkType.think);
        await thinking.future;
      };
    addTearDown(provider.dispose);
    final video = MessageFile('', null, 'finish.jpg', 'image/jpeg', 'vid-1', DateTime.utc(2026, 10, 22), null,
        videoDurationSeconds: 14, localPreviewPath: poster.path);
    provider.uploadedFiles.add(video);

    await tester.pumpWidget(_chat(provider));
    await tester.pump();
    provider.addMessageLocally('What do you see here?');
    unawaited(provider.sendMessageStreamToServer('What do you see here?'));
    await tester.pump();
    // Let the real file read and image decode finish outside fake time.
    for (var i = 0; i < 5; i++) {
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pump();
    }
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byIcon(Icons.play_arrow), findsOneWidget);
    expect(find.text('0:14'), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.chat.stop')), findsOneWidget);
    expect(tester.takeException(), isNull);

    if (output.isNotEmpty) {
      await tester.runAsync(() async {
        final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/001-mobile-ios-chat-video-poster-and-stop.png').writeAsBytes(bytes!.buffer.asUint8List());
      });
    }
    unawaited(provider.stopReply());
    await tester.pump();
    await tester.pump();
    debugDefaultTargetPlatformOverride = null;
  });
}

final class _EnvFields implements EnvFields {
  const _EnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
