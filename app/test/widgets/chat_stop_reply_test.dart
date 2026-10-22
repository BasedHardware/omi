import 'dart:async';

import 'package:flutter/material.dart';
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
import 'package:omi/utils/platform/platform_manager.dart';

ServerMessage _textMessage(String id, DateTime createdAt, String text, MessageSender sender) {
  return ServerMessage(id, createdAt, text, sender, MessageType.text, null, false, [], [], []);
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
        child: const ChatPage(),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(const _EnvFields());
  });

  setUp(() async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('while Omi answers, Stop ends the reply and a typed message replaces it', (tester) async {
    tester.view.physicalSize = const Size(400, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final sent = <String>[];
    final thinking = Completer<void>();
    final provider = _QuietMessages(_OlderSessions(const []))
      ..chatSessionId = 'session-1'
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        sent.add(text);
        if (text.startsWith('Is this one steel')) {
          yield ServerMessageChunk('r1', 'Searching', MessageChunkType.think);
          await thinking.future;
        }
        yield ServerMessageChunk(
          'r2',
          '',
          MessageChunkType.done,
          message: _textMessage('r2', DateTime.utc(2026, 10, 22), 'Here is the progression.', MessageSender.ai),
        );
      };
    addTearDown(provider.dispose);

    await tester.pumpWidget(_chat(provider));
    await tester.pump();

    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), 'Is this one steel frame?');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump();
    await tester.pump();

    expect(provider.canStopReply, isTrue);
    expect(find.byKey(const ValueKey('omi.chat.stop')), findsOneWidget, reason: 'an empty composer offers Stop');

    // Typing a correction swaps Stop for Send, which replaces the running reply.
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), 'Sorry, I meant still frame');
    await tester.pump();
    expect(find.byKey(const ValueKey('omi.chat.stop')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(sent, ['Is this one steel frame?', 'Sorry, I meant still frame']);
    expect(find.text('Is this one steel frame?'), findsOneWidget, reason: 'the first question stays');
    expect(find.text('Here is the progression.'), findsOneWidget);
    expect(provider.canStopReply, isFalse);
    expect(find.byKey(const ValueKey('omi.chat.stop')), findsNothing);
  });

  testWidgets('Stop with an empty composer ends a reply that is still thinking', (tester) async {
    tester.view.physicalSize = const Size(400, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final never = Completer<void>();
    final provider = _QuietMessages(_OlderSessions(const []))
      ..chatSessionId = 'session-1'
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r1', 'Searching', MessageChunkType.think);
        await never.future;
      };
    addTearDown(provider.dispose);

    await tester.pumpWidget(_chat(provider));
    await tester.pump();
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), 'What do you see here?');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('omi.chat.stop')));
    await tester.pump();
    await tester.pump();

    expect(provider.canStopReply, isFalse);
    expect(provider.showTypingIndicator, isFalse);
    expect(find.text('What do you see here?'), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.chat.stop')), findsNothing);
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
