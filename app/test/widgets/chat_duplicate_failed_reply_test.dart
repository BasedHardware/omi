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
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/ui/ui.dart';
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

  testWidgets('two failed replies keep their Try Again rows when older history is prepended', (tester) async {
    tester.view.physicalSize = const Size(400, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final older = _textMessage('older-1', DateTime.utc(2024, 5, 1), 'Older history', MessageSender.human);
    final provider = _QuietMessages(_OlderSessions([older]))
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        throw const ChatStreamException(ChatStreamFailureClass.offline);
      }
      ..chatSessionId = 'session-1'
      ..hasOlderMessages = true;
    addTearDown(provider.dispose);

    provider.addMessageLocally('First question');
    await provider.sendMessageStreamToServer('First question');
    provider.addMessageLocally('Second question');
    await provider.sendMessageStreamToServer('Second question');

    final mounted = DateTime.utc(2024, 6, 1);
    for (var i = 0; i < provider.messages.length; i++) {
      provider.messages[i].createdAt = mounted.add(Duration(minutes: i));
    }
    final idsBefore = provider.messages.map((message) => message.id).toList();
    final failedBefore = provider.messages.where(provider.isReplyFailed).toList();
    expect(idsBefore, [isNot('0000'), '0000', isNot('0000'), '0000']);
    expect(failedBefore, hasLength(2));
    expect(failedBefore.map((message) => message.id), everyElement('0000'));

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
    await tester.pump();

    expect(find.byType(ChatReplyError), findsNWidgets(2));
    expect(find.text('Try Again'), findsNWidgets(2));
    expect(find.text('Unable to connect. Check your connection and try again.'), findsNWidgets(2));

    await tester.tap(find.byKey(const Key('chat_load_older')));
    await tester.pump();

    expect(provider.messages.map((message) => message.id).toList(), ['older-1', ...idsBefore]);
    final failedAfter = provider.messages.where(provider.isReplyFailed).toList();
    expect(failedAfter, hasLength(2));
    expect(identical(failedAfter[0], failedBefore[0]), isTrue);
    expect(identical(failedAfter[1], failedBefore[1]), isTrue);
    expect(find.text('Older history'), findsOneWidget);
    expect(find.text('First question'), findsOneWidget);
    expect(find.text('Second question'), findsOneWidget);
    expect(find.byType(ChatReplyError), findsNWidgets(2));
    expect(find.text('Try Again').hitTestable(), findsNWidgets(2));
    final retries = tester.widgetList<OmiButton>(find.widgetWithText(OmiButton, 'Try Again')).toList();
    expect(retries, hasLength(2));
    expect(retries.every((button) => button.onPressed != null), isTrue);

    provider.replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
      yield ServerMessageChunk(
        'recovered',
        '',
        MessageChunkType.done,
        message: _textMessage('recovered', DateTime.utc(2024, 6, 2), 'Recovered answer', MessageSender.ai),
      );
    };
    await tester.tap(find.text('Try Again').first);
    await tester.pump();

    expect(find.text('Recovered answer'), findsOneWidget);
    expect(find.text('First question'), findsOneWidget);
    expect(find.text('Second question'), findsOneWidget);
    expect(find.byType(ChatReplyError), findsOneWidget);
    expect(find.text('Try Again').hitTestable(), findsOneWidget);
    expect(provider.isReplyFailed(failedBefore[1]), isTrue);
    expect(provider.messages.any((message) => message.id == 'recovered'), isTrue);
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
