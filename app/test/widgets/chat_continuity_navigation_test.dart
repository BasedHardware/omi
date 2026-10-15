import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Keep real popup navigation, composer and send state; only backend I/O is replaced.
class _Messages extends MessageProvider {
  _Messages(ChatSessionsApi api) : super(sessionsApi: api);
  @override
  Future<void> fetchChatApps() async {}

  int refreshCalls = 0;
  @override
  Future<void> refreshMessages({bool dropdownSelected = false}) async {
    refreshCalls++; // The current-thread read is empty in this widget fixture.
  }
}

class _HistoryServer {
  final requests = <ApiRequest>[];
  int readStatus = 200;

  http.Response transcript(String id) => http.Response(
      jsonEncode([
        {
          'id': '$id-question',
          'text': 'Question from $id',
          'sender': 'human',
          'created_at': '2026-09-29T01:00:00Z',
          'type': 'text',
        },
        {
          'id': '$id-answer',
          'text': 'Answer from $id',
          'sender': 'ai',
          'created_at': '2026-09-29T01:01:00Z',
          'type': 'text',
          'content_blocks': [
            {'type': 'followUp', 'text': 'What should I do next?'}
          ],
        },
      ]),
      readStatus);

  Future<http.Response> send(ApiRequest request) async {
    requests.add(request);
    final uri = Uri.parse(request.url);
    if (request.method != 'GET') throw StateError('Opening history must be read-only: ${request.method}');
    if (uri.path == '/v2/chat-sessions') {
      return http.Response(
          jsonEncode([
            for (final id in ['first', 'second'])
              {'id': id, 'title': 'Saved $id', 'message_count': 2, 'updated_at': '2026-09-29T01:01:00Z'},
          ]),
          200);
    }
    if (uri.path == '/v2/messages') {
      return transcript(uri.queryParameters['chat_session_id']!);
    }
    throw StateError('Unexpected request: ${uri.path}');
  }
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    PlatformManager.initializeForLocalHarness();
  });

  Future<_Messages> pumpChat(WidgetTester tester, _HistoryServer server, {String? draft, bool empty = false}) async {
    final provider = _Messages(ChatSessionsApi(baseUrl: 'https://example.invalid/', send: server.send))
      ..messages = [
        ServerMessage('current', DateTime.utc(2026), 'Current conversation', MessageSender.human, MessageType.text,
            null, false, [], [], []),
      ];
    if (empty) provider.messages.clear();
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<MessageProvider>(create: (_) => provider),
        ChangeNotifierProvider(create: (_) => AppProvider()),
        ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ChangeNotifierProvider(create: (_) => HomeProvider()),
        ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
        ChangeNotifierProvider(create: (_) => ConversationProvider(isSignedIn: () => false)),
        ChangeNotifierProvider(
            create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {})),
      ],
      child: MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () => openChatSheet<void>(context, ChatPage(initialDraft: draft)),
                    child: const Text('Open chat')))),
      ),
    ));
    await tester.tap(find.text('Open chat'));
    await tester.pumpAndSettle();
    return provider;
  }

  Future<void> seedReply(WidgetTester tester) async {
    final provider = tester.element(find.byType(ChatPage)).read<MessageProvider>();
    provider.messages = (jsonDecode(_HistoryServer().transcript('first').body) as List)
        .map((row) => ServerMessage.fromJson(row as Map<String, dynamic>))
        .toList();
    provider.notifyListeners();
    await tester.pumpAndSettle();
  }

  testWidgets('closing and reopening chat keeps the same messages without creating a session', (tester) async {
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server);
    final messages = provider.messages;
    for (var i = 0; i < 3; i++) {
      await tester.tap(find.byKey(const Key('chat_close')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open chat'));
      await tester.pumpAndSettle();
      expect(identical(provider.messages, messages), isTrue);
      expect(find.text('Current conversation'), findsOneWidget);
      expect(provider.isFreshChat, isFalse);
      expect(provider.chatSessionId, isNull);
    }
    expect(server.requests, isEmpty);
    expect(provider.refreshCalls, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('single chat has no history control and keeps its dismissal handle centered', (tester) async {
    await pumpChat(tester, _HistoryServer());
    expect(find.byKey(const Key('chat_history')), findsNothing);
    expect(find.text('Past chats'), findsNothing);
    expect(find.text('New Chat'), findsNothing);
    expect(tester.getCenter(find.byKey(const Key('chat_drag_handle'))).dx,
        closeTo(tester.getCenter(find.byType(ChatPage)).dx, 1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('an empty provider reloads the current chat without marking it as a new session', (tester) async {
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server, empty: true);
    expect(provider.refreshCalls, 1);
    expect(provider.isFreshChat, isFalse);
    expect(provider.chatSessionId, isNull);
    expect(server.requests, isEmpty);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a starter and typed draft survive tapping the composer and keyboard resizing', (tester) async {
    final server = _HistoryServer();
    await pumpChat(tester, server, empty: true);
    await tester.tap(find.byKey(const Key('chat_starter_goal')));
    await tester.pumpAndSettle();
    final input = find.byKey(const ValueKey('omi.chat.input'));
    String draft() => tester.widget<TextField>(input).controller!.text;
    expect(draft(), 'Help me set a goal');
    await tester.tap(input);
    await tester.enterText(input, 'Help me set a goal for tomorrow');
    tester.view.viewInsets = const FakeViewPadding(bottom: 250);
    addTearDown(tester.view.resetViewInsets);
    await tester.pumpAndSettle();
    await tester.tap(input);
    await tester.pumpAndSettle();
    expect(draft(), 'Help me set a goal for tomorrow');
    expect(server.requests, isEmpty, reason: 'Selecting or editing a starter does not send or delete');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('reopening during a send preserves the active reply and conversation', (tester) async {
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server);
    provider.setSendingMessage(true);
    await tester.pump();
    await tester.tap(find.byKey(const Key('chat_close')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open chat'));
    await tester.pumpAndSettle();
    expect(provider.sendingMessage, isTrue);
    expect(provider.messages.single.text, 'Current conversation');
    expect(provider.isFreshChat, isFalse);
    expect(server.requests, isEmpty);
    provider.setSendingMessage(false);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Send stays enabled while history is still loading and reaches the streamer', (tester) async {
    final provider = await pumpChat(tester, _HistoryServer());
    provider.isLoadingMessages = true;
    provider.notifyListeners();
    await tester.pump();

    final sends = <String>[];
    provider.replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
      sends.add(text);
      yield ServerMessageChunk(
        'answer',
        'Done',
        MessageChunkType.done,
        message: ServerMessage('answer', DateTime.utc(2026, 9, 29, 2), 'Done', MessageSender.ai, MessageType.text, null,
            false, [], [], []),
      );
    };
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), 'hello while loading');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await tester.pumpAndSettle();

    expect(sends, ['hello while loading']);
    expect(provider.isLoadingMessages, isFalse);
    expect(provider.messages.last.text, 'Done');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('tapping a follow-up sends it once in the continuous chat and retains the previous messages',
      (tester) async {
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server);
    await seedReply(tester);
    final sends = <(String, String?)>[];
    provider.replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
      sends.add((text, chatSessionId));
      yield ServerMessageChunk('followup-answer', 'Next step reply', MessageChunkType.done,
          message: ServerMessage('followup-answer', DateTime.utc(2026, 9, 29, 2), 'Next step reply', MessageSender.ai,
              MessageType.text, null, false, [], [], []));
    };
    await tester.ensureVisible(find.byKey(const Key('chat_followup_chip')));
    await tester.tap(find.byKey(const Key('chat_followup_chip')));
    await tester.pumpAndSettle();
    expect(sends, [('What should I do next?', null)]);
    expect(provider.messages.map((m) => m.text), [
      'Question from first',
      'Answer from first',
      'What should I do next?',
      'Next step reply',
    ]);
    expect(provider.sendingMessage, isFalse);
    expect(find.byKey(const Key('chat_followup_chip')), findsNothing,
        reason: 'The used suggestion disappears when a newer answer has no follow-up');
    expect(server.requests.every((r) => r.method == 'GET'), isTrue);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('only the latest reply suggests a question above the composer, including with the keyboard open',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server);
    await seedReply(tester);
    final older = ServerMessage('older-reply', DateTime.utc(2026), 'An earlier answer', MessageSender.ai,
        MessageType.text, null, false, [], [], [],
        contentBlocks: [
          {'type': 'followUp', 'text': 'An outdated suggestion?'},
        ]);
    provider.messages.insert(0, older);
    provider.notifyListeners();
    await tester.pumpAndSettle();
    final chip = find.byKey(const Key('chat_followup_chip'));
    expect(chip, findsOneWidget);
    expect(find.text('An outdated suggestion?'), findsNothing);
    expect(find.descendant(of: find.byType(AIMessage), matching: chip), findsNothing,
        reason: 'Suggestions belong to the composer, never to historical message rows');
    expect(tester.getBottomLeft(chip).dy,
        lessThanOrEqualTo(tester.getTopLeft(find.byKey(const ValueKey('omi.chat.input'))).dy));
    await tester.tap(find.byKey(const ValueKey('omi.chat.input')));
    tester.view.viewInsets = const FakeViewPadding(bottom: 300);
    addTearDown(tester.view.resetViewInsets);
    await tester.pumpAndSettle();
    expect(chip.hitTestable(), findsOneWidget);
    expect(tester.getBottomLeft(chip).dy,
        lessThanOrEqualTo(tester.getTopLeft(find.byKey(const ValueKey('omi.chat.input'))).dy));
    expect(older.followUpQuestion, 'An outdated suggestion?', reason: 'Saved message data is preserved');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a new turn hides the old suggestion while streaming and replaces it only after completion',
      (tester) async {
    final server = _HistoryServer();
    final provider = await pumpChat(tester, server);
    await seedReply(tester);
    provider.setSendingMessage(true);
    await tester.pump();
    expect(find.byKey(const Key('chat_followup_chip')), findsNothing);
    provider.addMessageLocally('My next question');
    final next = ServerMessage('next-answer', DateTime.utc(2026, 9, 29, 2), 'A newer answer', MessageSender.ai,
        MessageType.text, null, false, [], [], [],
        contentBlocks: [
          {'type': 'followUp', 'text': 'A new suggestion?'},
        ]);
    provider.addMessage(next);
    provider.setShowTypingIndicator(true);
    provider.setSendingMessage(false);
    await tester.pump();
    expect(find.byKey(const Key('chat_followup_chip')), findsNothing);
    provider.setShowTypingIndicator(false);
    await tester.pumpAndSettle();
    expect(find.text('A new suggestion?'), findsOneWidget);
    expect(find.text('What should I do next?'), findsNothing);
    provider.addMessageLocally('Another question');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chat_followup_chip')), findsNothing,
        reason: 'A trailing user message must never revive the previous suggestion');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a long pinned suggestion fits a small screen with large text and the keyboard open', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetViewInsets);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final provider = await pumpChat(tester, _HistoryServer());
    await seedReply(tester);
    await tester.tap(find.byKey(const ValueKey('omi.chat.input')));
    tester.view.viewInsets = const FakeViewPadding(bottom: 220);
    const question = 'What was still undecided about the apps and\n\n'
        'integrations experience and the next review?';
    final sends = <(String, String?)>[];
    provider.replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
      sends.add((text, chatSessionId));
      yield ServerMessageChunk('next-answer', 'Next answer', MessageChunkType.done,
          message: ServerMessage('next-answer', DateTime.utc(2026, 9, 29, 3), 'Next answer', MessageSender.ai,
              MessageType.text, null, false, [], [], []));
    };
    provider.addMessage(ServerMessage('long-answer', DateTime.utc(2026, 9, 29, 2), 'Here is the answer',
        MessageSender.ai, MessageType.text, null, false, [], [], [],
        contentBlocks: [
          {'type': 'followUp', 'text': question},
        ]));
    await tester.pumpAndSettle();
    final chip = find.byKey(const Key('chat_followup_chip'));
    expect(chip, findsOneWidget);
    final bounds = tester.getRect(chip);
    expect(bounds.left, greaterThanOrEqualTo(12));
    expect(bounds.right, lessThanOrEqualTo(308), reason: 'The full suggestion control stays inside the 320pt screen');
    expect(bounds.height, lessThanOrEqualTo(80), reason: 'A short viewport uses one line to leave room for reading');
    expect(find.byKey(const ValueKey('omi.chat.input')).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(sends, [(question, null)], reason: 'An abbreviated preview must send the complete original question');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('pulling down from the header closes chat; nudges and transcript drags do not', (tester) async {
    final server = _HistoryServer();
    await pumpChat(tester, server);
    final handle = find.byKey(const Key('chat_drag_handle'));
    await tester.drag(handle, const Offset(0, -90));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsOneWidget);
    await tester.drag(handle, const Offset(0, 20));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsOneWidget);
    await tester.drag(find.text('Current conversation'), const Offset(0, 100));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsOneWidget);
    await tester.drag(handle, const Offset(0, 220));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsNothing);
    expect(find.text('Open chat'), findsOneWidget);
    expect(server.requests, isEmpty);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the popup tracks the finger and a short drag settles back without losing the draft', (tester) async {
    await pumpChat(tester, _HistoryServer(), draft: 'Keep this draft');
    final page = find.byType(ChatPage);
    final navigator = Navigator.of(tester.element(page));
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('chat_drag_handle'))));
    await gesture.moveBy(const Offset(0, 90));
    await tester.pump();
    expect(tester.getTopLeft(page).dy, closeTo(90, 1));
    await gesture.moveBy(const Offset(0, -30));
    await tester.pump();
    expect(tester.getTopLeft(page).dy, closeTo(60, 1));
    await tester.pump(const Duration(milliseconds: 200));
    await gesture.up();
    await tester.pump(const Duration(milliseconds: 60));
    expect(tester.getTopLeft(page).dy, inExclusiveRange(0, 60));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(page).dy, closeTo(0, 1));
    expect(navigator.userGestureInProgress, isFalse);
    expect(tester.widget<TextField>(find.byKey(const ValueKey('omi.chat.input'))).controller!.text, 'Keep this draft');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a cancelled pointer restores the popup and a committed pull continues from its release position',
      (tester) async {
    await pumpChat(tester, _HistoryServer());
    final page = find.byType(ChatPage);
    final navigator = Navigator.of(tester.element(page));
    final handle = find.byKey(const Key('chat_drag_handle'));
    var gesture = await tester.startGesture(tester.getCenter(handle));
    await gesture.moveBy(const Offset(0, 90));
    await tester.pump();
    await gesture.cancel();
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(page).dy, closeTo(0, 1));
    expect(navigator.userGestureInProgress, isFalse);
    gesture = await tester.startGesture(tester.getCenter(handle));
    await gesture.moveBy(const Offset(0, 240));
    await tester.pump();
    final releaseY = tester.getTopLeft(page).dy;
    await tester.pump(const Duration(milliseconds: 200));
    await gesture.up();
    await tester.pump();
    expect(tester.getTopLeft(page).dy, closeTo(releaseY, 1), reason: 'Closing must not jump back to the top');
    await tester.pump(const Duration(milliseconds: 60));
    expect(tester.getTopLeft(page).dy, greaterThan(releaseY));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsNothing);
    expect(navigator.userGestureInProgress, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a route removed mid-drag releases its gesture without popping the parent twice', (tester) async {
    await pumpChat(tester, _HistoryServer());
    final navigator = Navigator.of(tester.element(find.byType(ChatPage)));
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('chat_drag_handle'))));
    await gesture.moveBy(const Offset(0, 80));
    await tester.pump();
    navigator.pop();
    await gesture.cancel();
    await tester.pumpAndSettle();
    expect(find.text('Open chat'), findsOneWidget);
    expect(navigator.canPop(), isFalse);
    expect(navigator.userGestureInProgress, isFalse);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Reduce Motion keeps the popup stationary during a pull and still permits dismissal', (tester) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    await pumpChat(tester, _HistoryServer());
    final page = find.byType(ChatPage);
    final navigator = Navigator.of(tester.element(page));
    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('chat_drag_handle'))));
    await gesture.moveBy(const Offset(0, 240));
    await tester.pump();
    expect(tester.getTopLeft(page).dy, 0);
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.byType(ChatPage), findsNothing);
    expect(navigator.userGestureInProgress, isFalse);
    await tester.pumpWidget(const SizedBox());
  });
}
