import 'dart:async';
import 'dart:collection';

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
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
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

// Count membership walks separately from O(visible rows) indexed slot reads.
class _History extends ListBase<ServerMessage> {
  _History(this.values);
  final List<ServerMessage> values;
  int visited = 0;
  @override
  int get length => values.length;
  @override
  set length(int value) => values.length = value;
  @override
  ServerMessage operator [](int index) => values[index];
  @override
  void operator []=(int index, ServerMessage value) => values[index] = value;
  @override
  Iterator<ServerMessage> get iterator => values.map((message) {
        visited++;
        return message;
      }).iterator;
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

  void ping() => notifyListeners();
}

class _StaticVoice extends ChangeNotifier implements VoiceRecorderProvider {
  _StaticVoice(this.state);
  @override
  final VoiceRecorderState state;
  @override
  List<double> get audioLevels => const [0.1, 0.2, 0.1];
  @override
  final ValueNotifier<int> waveformTick = ValueNotifier<int>(0);
  @override
  void setCallbacks({Function(String transcript, bool autoSend)? onTranscriptReady, VoidCallback? onClose}) {}
  @override
  void dispose() {
    waveformTick.dispose();
    super.dispose();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
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
  setUpAll(() => Env.init(const _EnvFields()));
  setUp(() async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });
  for (final semantics in [false, true]) {
    testWidgets('stream updates leave chat shell and settled markdown alone, semantics=$semantics', (tester) async {
      addTearDown(tester.view.resetViewInsets);
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final provider = _QuietMessages(_OlderSessions(const []));
        addTearDown(provider.dispose);
        final history = _History(List.generate(
            80, (i) => _textMessage('m$i', DateTime.utc(2026, 10, 22), '**Settled $i** paragraph', MessageSender.ai)));
        provider.messages = history;

        await tester.pumpWidget(_chat(provider));
        await tester.pump(const Duration(seconds: 1));
        await tester.pump(const Duration(seconds: 1));
        final counts = <String, int>{};
        history.visited = 0;
        debugOnRebuildDirtyWidget = (element, builtOnce) {
          final name = element.widget.runtimeType.toString();
          counts[name] = (counts[name] ?? 0) + 1;
        };
        addTearDown(() => debugOnRebuildDirtyWidget = null);
        for (var i = 0; i < 10; i++) {
          provider.ping();
          await tester.pump();
        }
        debugPrint(
            'CHAT_NOOP semantics=$semantics history_visits=${history.visited} header=${counts['ChatHeader'] ?? 0} scaffold=${counts['Scaffold'] ?? 0} ai=${counts['AIMessage'] ?? 0} markdown=${counts['MarkdownBody'] ?? 0} total=${counts.values.fold(0, (int a, b) => a + b)}');
        final noOpHeader = counts['ChatHeader'] ?? 0;
        final noOpVisits = history.visited;
        counts.clear();
        history.visited = 0;
        for (var i = 0; i < 10; i++) {
          provider.messages.last.text += ' chunk';
          provider.ping();
          await tester.pump(const Duration(milliseconds: 100));
        }
        debugPrint(
            'CHAT_STREAM semantics=$semantics header=${counts['ChatHeader'] ?? 0} scaffold=${counts['Scaffold'] ?? 0} ai=${counts['AIMessage'] ?? 0} markdown=${counts['MarkdownBody'] ?? 0} history_visits=${history.visited} slots=${counts['_ChatMessageSlot'] ?? 0} total=${counts.values.fold(0, (int a, b) => a + b)}');
        final streamCounts = Map<String, int>.of(counts);
        final streamVisits = history.visited;
        counts.clear();
        history.visited = 0;
        tester.view.viewInsets = const FakeViewPadding(bottom: 300);
        await tester.pump();
        debugPrint(
            'CHAT_KEYBOARD semantics=$semantics history_visits=${history.visited} header=${counts['ChatHeader'] ?? 0} ai=${counts['AIMessage'] ?? 0} markdown=${counts['MarkdownBody'] ?? 0} total=${counts.values.fold(0, (int a, b) => a + b)}');
        final openVisits = history.visited;
        history.visited = 0;
        tester.view.resetViewInsets();
        await tester.pump();
        debugPrint('CHAT_KEYBOARD_CLOSE semantics=$semantics history_visits=${history.visited}');
        expect(openVisits, 0, reason: 'keyboard opening must reuse transcript membership');
        expect(history.visited, 0, reason: 'keyboard closing must reuse transcript membership');
        expect(noOpHeader, 0);
        expect(noOpVisits, 0, reason: 'no-op notifications must not walk chat history');
        expect(streamVisits, 0);
        expect(streamCounts['ChatHeader'] ?? 0, 0);
        expect(streamCounts['Scaffold'] ?? 0, 0);
        expect(streamCounts['MarkdownBody'] ?? 0, lessThanOrEqualTo(10));
        tester.view.resetViewInsets();
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump(const Duration(seconds: 1));
      } finally {
        handle?.dispose();
      }
    });
  }

  testWidgets('free-scrolling stays put through streamed text, append and keyboard', (tester) async {
    addTearDown(tester.view.resetViewInsets);
    final provider = _QuietMessages(_OlderSessions(const []));
    addTearDown(provider.dispose);
    provider.messages =
        List.generate(80, (i) => _textMessage('m$i', DateTime.utc(2026), '**Settled $i** paragraph', MessageSender.ai));
    await tester.pumpWidget(_chat(provider));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    final controller = tester.state<ChatPageState>(find.byType(ChatPage)).scrollController;
    expect(controller.offset, greaterThan(0));
    await tester.drag(find.byType(ListView).first, const Offset(0, 300));
    await tester.pumpAndSettle();
    final before = controller.offset;
    for (var i = 0; i < 10; i++) {
      provider.messages.last.text += ' chunk';
      provider.ping();
      await tester.pump(const Duration(milliseconds: 100));
    }
    provider.addMessage(_textMessage('appended', DateTime.utc(2026), 'New answer', MessageSender.ai));
    await tester.pump();
    tester.view.viewInsets = const FakeViewPadding(bottom: 300);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    debugPrint('CHAT_FREE_SCROLL offset_before=$before offset_after=${controller.offset}');
    expect(controller.offset, closeTo(before, 1));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('following scroll uses the extent after the streamed message is laid out', (tester) async {
    final provider = _QuietMessages(_OlderSessions(const []));
    addTearDown(provider.dispose);
    provider.messages =
        List.generate(40, (i) => _textMessage('m$i', DateTime.utc(2026), '**Settled $i** paragraph', MessageSender.ai));
    await tester.pumpWidget(_chat(provider));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    final controller = tester.state<ChatPageState>(find.byType(ChatPage)).scrollController;
    final before = controller.position.maxScrollExtent;
    for (var frame = 0; frame < 3; frame++) {
      for (var chunk = 0; chunk < 3; chunk++) {
        provider.messages.last.text += '\n\nA streamed paragraph with enough text to wrap on the screen.';
        provider.ping();
      }
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
    }
    debugPrint(
        'CHAT_FOLLOW extent_growth=${controller.position.maxScrollExtent - before} distance_from_bottom=${controller.position.maxScrollExtent - controller.offset}');
    expect(controller.position.maxScrollExtent, greaterThan(before));
    expect(controller.position.maxScrollExtent - controller.offset, lessThanOrEqualTo(24));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });
  testWidgets('real reply-stream buffer notifies update only the streaming slot', (tester) async {
    final chunks = StreamController<ServerMessageChunk>();
    final provider = _QuietMessages(_OlderSessions(const []))
      ..chatSessionId = 'perf-session'
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) => chunks.stream;
    addTearDown(provider.dispose);
    provider.messages = [_textMessage('old', DateTime.utc(2026), '**Settled history**', MessageSender.ai)];
    await tester.pumpWidget(_chat(provider));
    await tester.pump(const Duration(seconds: 1));
    final turn = provider.sendMessageStreamToServer('Question');
    await tester.pump();
    await tester.pump();
    var headers = 0;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      if (element.widget.runtimeType.toString() == 'ChatHeader') headers++;
    };
    addTearDown(() => debugOnRebuildDirtyWidget = null);
    for (var i = 0; i < 10; i++) {
      chunks.add(ServerMessageChunk('live', 'chunk ', MessageChunkType.data));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
    }
    debugPrint('CHAT_REAL_STREAM chunks=10 header_builds=$headers text_length=${provider.messages.last.text.length}');
    final streamHeaders = headers;
    debugOnRebuildDirtyWidget = null;
    unawaited(provider.stopReply());
    await tester.pump();
    await tester.pump();
    await turn;
    unawaited(chunks.close());
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
    expect(streamHeaders, 0);
  });

  for (final state in [VoiceRecorderState.recording, VoiceRecorderState.pendingRecovery]) {
    testWidgets('static voice composer has no unused animation ticker: $state', (tester) async {
      final voice = _StaticVoice(state);
      addTearDown(voice.dispose);
      final baseline = tester.binding.transientCallbackCount;
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: ChangeNotifierProvider<VoiceRecorderProvider>.value(
          value: voice,
          child: Scaffold(body: VoiceRecorderWidget(onTranscriptReady: (_, __) {}, onClose: () {})),
        ),
      ));
      var callbacks = 0;
      for (var i = 0; i < 60; i++) {
        await tester.pump(const Duration(milliseconds: 16));
        callbacks += tester.binding.transientCallbackCount - baseline;
      }
      debugPrint('CHAT_VOICE state=$state unused_callbacks_60_frames=$callbacks');
      await tester.pumpWidget(const SizedBox.shrink());
      expect(callbacks, 0);
    });
  }
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
