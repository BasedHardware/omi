import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/streaming_error.dart';
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

class _Sessions extends ChatSessionsApi {
  @override
  Future<ApiResult<List<ServerMessage>>> messages(String id, {int offset = 0, int limit = 100}) async =>
      const ApiSuccess([]);

  @override
  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) async => const ApiSuccess('Title');
}

class _QuietMessages extends MessageProvider {
  _QuietMessages() : super(sessionsApi: _Sessions());

  @override
  Future<void> fetchChatApps() async {}

  @override
  Future refreshMessages({bool dropdownSelected = false}) async {}
}

ServerMessage _aiMessage(String text) {
  return ServerMessage(
      'reply-$text', DateTime.utc(2026, 10, 29), text, MessageSender.ai, MessageType.text, null, false, [], [], []);
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

/// Typed chat input must survive app close/kill: the composer draft is
/// persisted and restored on open, and the persisted copy is cleared only
/// after a send is accepted — a failed or refused send keeps it.
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

  Future<void> mountChat(WidgetTester tester, MessageProvider provider) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      builder: (context, child) {
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: child!,
        );
      },
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
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
  }

  Future<void> sendText(WidgetTester tester, String text) async {
    await tester.enterText(find.byType(TextField), text);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
  }

  testWidgets('a persisted draft is restored when chat opens', (tester) async {
    SharedPreferencesUtil().chatMessageDraft = 'half-written question';
    final provider = _QuietMessages();
    addTearDown(provider.dispose);

    await mountChat(tester, provider);

    expect(find.text('half-written question'), findsOneWidget);
  });

  testWidgets('an empty persisted draft does not resurrect stale text', (tester) async {
    final provider = _QuietMessages();
    addTearDown(provider.dispose);

    await mountChat(tester, provider);

    expect(SharedPreferencesUtil().chatMessageDraft, '');
  });

  testWidgets('a failed send keeps the persisted draft for restore', (tester) async {
    final provider = _QuietMessages()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        throw const ChatStreamException(ChatStreamFailureClass.offline);
      };
    addTearDown(provider.dispose);

    await mountChat(tester, provider);
    await sendText(tester, 'please do not lose this');

    expect(SharedPreferencesUtil().chatMessageDraft, 'please do not lose this',
        reason: 'a failed send must keep the draft restorable');
  });

  testWidgets('an accepted send clears the persisted draft', (tester) async {
    final provider = _QuietMessages()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk(
          'recovered',
          '',
          MessageChunkType.done,
          message: _aiMessage('Received'),
        );
      };
    addTearDown(provider.dispose);

    await mountChat(tester, provider);
    await sendText(tester, 'delivered message');

    expect(SharedPreferencesUtil().chatMessageDraft, '', reason: 'the draft is cleared only after acceptance');
    expect(find.text('delivered message'), findsOneWidget);
  });

  testWidgets('a newer draft typed while the reply streams is never clobbered', (tester) async {
    final replyStarted = Completer<void>();
    final letReplyFinish = Completer<void>();
    final provider = _QuietMessages()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        if (!replyStarted.isCompleted) replyStarted.complete();
        await letReplyFinish.future;
        yield ServerMessageChunk(
          'recovered',
          '',
          MessageChunkType.done,
          message: _aiMessage('Received'),
        );
      };
    addTearDown(provider.dispose);

    await mountChat(tester, provider);
    await tester.enterText(find.byType(TextField), 'first message');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump();
    await replyStarted.future;

    // The user starts a second draft while the first reply is still streaming.
    await tester.enterText(find.byType(TextField), 'second draft');
    await tester.pump(const Duration(milliseconds: 400));
    expect(SharedPreferencesUtil().chatMessageDraft, 'second draft');

    letReplyFinish.complete();
    await tester.pump(const Duration(seconds: 2));

    expect(SharedPreferencesUtil().chatMessageDraft, 'second draft',
        reason: 'the accepted first send must not erase the newer draft');
  });

  testWidgets('a send fired inside the debounce window still flushes its own draft', (tester) async {
    SharedPreferencesUtil().chatMessageDraft = 'old draft';
    final provider = _QuietMessages()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        throw const ChatStreamException(ChatStreamFailureClass.offline);
      };
    addTearDown(provider.dispose);

    await mountChat(tester, provider);
    // Type and send inside the 300ms debounce window, so the periodic save
    // never fires before the send does.
    await tester.enterText(find.byType(TextField), 'new draft');
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pump(const Duration(seconds: 2));

    expect(SharedPreferencesUtil().chatMessageDraft, 'new draft',
        reason: 'the send flushes its own draft synchronously; a failed send restores it, never the stale one');
  });
}
