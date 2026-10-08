import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/chat/widgets/chat_chrome.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/chat_message_native.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));
TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

ServerMessage _ai(String id, {String text = 'Here is the plan.', List<Map<String, dynamic>> blocks = const []}) =>
    ServerMessage.fromJson({
      'id': id,
      'created_at': '2026-09-02T12:00:00Z',
      'text': text,
      'sender': 'ai',
      'type': 'text',
      'content_blocks': blocks,
    });

ServerMessage _human(String id, String text) => ServerMessage(
    id, DateTime.utc(2026, 9, 2, 11), text, MessageSender.human, MessageType.text, null, false, [], [], []);

ActionItemWithMetadata _task(String id, {bool completed = false}) =>
    wire.GeneratedActionItemResponse(id: id, description: 'Send the launch email', completed: completed);

class _Tasks extends ActionItemsProvider {
  _Tasks(this._items)
      : super(
          getActionItems: ({
            int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate,
            DateTime? dueStartDate,
            DateTime? dueEndDate,
          }) async =>
              const wire.GeneratedActionItemsResponse(actionItems: []),
        );

  final List<ActionItemWithMetadata> _items;
  final updates = <(String, bool)>[];
  var loads = 0;
  Completer<void>? pending;

  @override
  List<ActionItemWithMetadata> get actionItems => _items;

  @override
  bool get isLoading => false;

  @override
  Future<void> ensureLoaded({bool showShimmer = false}) async => loads++;

  @override
  Future<bool> updateActionItemState(ActionItemWithMetadata item, bool newState) async {
    updates.add((item.id, newState));
    await pending?.future;
    return true;
  }
}

/// The real provider over a loaded transcript, without its history and chat-app reads.
class _PageMessages extends MessageProvider {
  @override
  Future<void> fetchChatApps() async {}

  @override
  Future refreshMessages({bool dropdownSelected = false}) async {}
}

class _Analytics implements AnalyticsAdapter {
  final events = <MapEntry<String, Map<String, Object>>>[];
  bool _ready = false;

  @override
  Future<void> init() async => _ready = true;
  @override
  bool get isInitialized => _ready;
  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}
  @override
  void alias({required String newUserId}) {}
  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add(MapEntry(eventName, properties ?? const {}));
  @override
  void enable() {}
  @override
  void disable() {}
  @override
  void reset() {}
  @override
  void registerSuperProperties(Map<String, Object> properties) {}
  @override
  void setInteractionContext({String? screenName, required String target}) {}
}

final class _AnotherOwner implements AuthTokenGateway {
  const _AnotherOwner();
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'another-owner');
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {}
}

/// Answers each 'present' on the config channel with [reply] and records the snapshots.
List<Map> _present(Map<String, Object?>? Function(Map snapshot) reply) {
  final presented = <Map>[];
  _messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    return reply(snapshot);
  });
  addTearDown(() => _messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

class _Harness {
  _Harness(this.messages);
  final MessageProvider messages;
  final transcript = <ChatNativeTranscript>[];
  late List<NativeRow> rows;
  final sent = <String>[];
  final quoted = <String>[];
  final ratings = <(int, String?)>[];
  final opened = <String>[];
  bool rated = true;
  ServerConversation? Function()? fetched;
  Completer<ServerConversation?>? fetching;

  NativeRow row(String id) => rows.singleWhere((row) => row.id == id);

  ChatNativeActions get actions => ChatNativeActions(
        send: sent.add,
        askOmi: quoted.add,
        retry: (_) async {},
        setMessageNps: (message, value, {reason}) async {
          ratings.add((value, reason));
          if (rated) message.rating = value == 0 ? null : value;
          return rated;
        },
        updateConversation: (_) {},
        openLink: (href) async => opened.add(href),
        fetchConversation: (_) => fetching?.future ?? Future.value(fetched?.call()),
      );
}

void main() {
  late ConversationProvider conversations;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'native-test-owner'});
    await SharedPreferencesUtil.init();
    conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);
  });

  Future<_Harness> pump(
    WidgetTester tester,
    List<ServerMessage> messages, {
    ActionItemsProvider? tasks,
    MessageProvider? provider,
  }) async {
    provider ??= MessageProvider()..messages = messages;
    final harness = _Harness(provider);
    final memories = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
    );
    final apps = AppProvider();
    final detail = ConversationDetailProvider()..setProviders(apps, conversations);
    addTearDown(() {
      detail.dispose();
      apps.dispose();
      memories.dispose();
    });
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
        ChangeNotifierProvider<MessageProvider>.value(value: provider),
        ChangeNotifierProvider<ActionItemsProvider>.value(value: tasks ?? _Tasks(const [])),
        ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
        ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
        ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: StatefulBuilder(builder: (context, setState) {
          if (harness.transcript.isEmpty) {
            harness.transcript.add(ChatNativeTranscript(onChanged: () => setState(() {})));
          }
          harness.rows = harness.transcript.single.rows(context, provider!, harness.actions);
          return const Scaffold(body: SizedBox());
        }),
      ),
    ));
    await tester.pump();
    addTearDown(() => harness.transcript.single.dispose());
    return harness;
  }

  Future<void> dispatch(_Harness harness, String id, Object? value) => dispatchNativeAction(
        MethodCall('action', {'id': id, 'value': value}),
        isActive: () => true,
        rows: harness.rows,
      );

  testWidgets('starters follow the classic transcript: only a chat with one message offers them', (tester) async {
    final first = await pump(tester, [_ai('a1')]);
    expect(first.rows.where((row) => row.id.startsWith('chat_starter_')).map((row) => row.title), [
      _l10n.chatStarterYesterday,
      _l10n.chatStarterDoDifferently,
      _l10n.chatStarterTeachMe,
    ]);
    await first.row('chat_starter_a1_1').action!(null);
    expect(first.sent, [_l10n.chatStarterDoDifferently]);

    final later = await pump(tester, [_human('h1', 'Hi'), _ai('a1')]);
    expect(later.rows.any((row) => row.id.startsWith('chat_starter_')), isFalse);
    final twoReplies = await pump(tester, [_ai('a1'), _ai('a2')]);
    expect(twoReplies.rows.any((row) => row.id.startsWith('chat_starter_')), isFalse,
        reason: 'the rule is the transcript length, not the position');
  });

  testWidgets('every row is valid and unique, and no block, task or conversation id becomes a row id', (tester) async {
    const blocks = [
      {'id': 'b-task', 'type': 'taskCard', 'taskId': 'task-secret-1'},
      {'id': 'b-link', 'type': 'conversationLink', 'conversationId': 'conversation-secret', 'summary': 'Planning'},
    ];
    final harness = await pump(tester, [
      _ai('0000', text: 'Two', blocks: blocks),
      _ai('0000', text: 'Two', blocks: blocks),
      _ai('a2', text: 'Three', blocks: blocks),
      _ai('a2~1', text: 'Four'),
      _ai('a2', text: 'Five'),
    ]);
    final ids = harness.rows.map((row) => row.id).toList();
    expect(ids.toSet(), hasLength(ids.length));
    expect(harness.rows.every((row) => row.valid), isTrue);
    expect(ids.where((id) => id.contains('b-task') || id.contains('secret') || id.contains('b-link')), isEmpty);
    expect(
        ids,
        containsAll([
          'chat_message_0000',
          'chat_message_0000~1',
          'chat_task_0000_0',
          'chat_task_0000~1_0',
          'chat_message_a2~1',
          'chat_message_a2~2',
        ]));
    for (final row in harness.rows) {
      expect(row.options.keys.any((key) => key.contains('secret')), isFalse);
    }
  });

  testWidgets('a rich body renders inline and opens only whitelisted links through the URL owner', (tester) async {
    final harness =
        await pump(tester, [_human('h1', 'Hi'), _ai('a1', text: '# Plan\n\n- [Docs](https://omi.me/docs)')]);
    final body = harness.row('chat_message_a1');
    expect(body.kind, 'message_ai');
    expect(body.plainText, isFalse);
    expect(body.blocks.map((block) => block['kind']), ['heading', 'text']);
    expect(body.symbol, isNull, reason: 'a successful reply has no trailing action');
    await dispatch(harness, 'chat_message_a1', 'https://omi.me/docs');
    expect(harness.opened, ['https://omi.me/docs']);
    await expectLater(dispatch(harness, 'chat_message_a1', 'https://evil.example'), throwsA(isA<PlatformException>()));
    expect(harness.opened, hasLength(1));
  });

  testWidgets('a body the native renderer cannot draw stays readable as literal text', (tester) async {
    final harness = await pump(tester, [
      _human('h1', 'Hi'),
      _ai('a1', text: 'See ![chart](http://insecure.example/c.png)'),
      _ai('a2', text: List.generate(2001, (i) => '- item $i').join('\n')),
    ]);
    expect(harness.row('chat_message_a1').blocks.any((block) => block['kind'] == 'image'), isFalse);
    expect(harness.row('chat_message_a1').valid, isTrue);
    expect(harness.row('chat_message_a2').plainText, isTrue);
    expect(harness.row('chat_message_a2').blocks, isEmpty);
    expect(harness.rows.every((row) => row.valid), isTrue);
  });

  testWidgets('a failed reply keeps Try Again with the localized reason', (tester) async {
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        throw Exception('socket closed');
      };
    provider.addMessageLocally('hello');
    await provider.sendMessageStreamToServer('hello');
    final harness = await pump(tester, provider.messages, provider: provider);
    final failed = provider.messages.last;
    final row = harness.row('chat_message_${failed.id}');
    expect(row.title, chatReplyFailureText(_l10n, provider.replyFailure(failed)));
    expect(row.symbol, 'arrow.clockwise');
    expect(row.plainText, isTrue);
    expect(row.enabled, isTrue);
    expect(harness.rows.where((row) => row.id.startsWith('chat_actions_${failed.id}')), isEmpty);
  });

  testWidgets('user context becomes a label before the bubble, and Ask Omi quotes the trimmed edit', (tester) async {
    NativeTestHost.install();
    final long = 'x' * 60;
    final harness = await pump(tester, [_human('h1', 'Context: "$long"\n\nWhat about this?')]);
    expect(harness.rows.map((row) => row.id), ['chat_context_h1_0', 'chat_message_h1', 'chat_ask_h1_0']);
    expect(harness.row('chat_context_h1_0').title, '${'x' * 50}…');
    expect(harness.row('chat_context_h1_0').symbol, 'arrow.turn.down.right');
    expect(harness.row('chat_message_h1').plainText, isTrue);

    final presented = _present((_) => {
          'action': 'ask',
          'values': {'chat_ask_text': '  about this  '},
          'reason': 'action',
        });
    await harness.row('chat_ask_h1_0').action!(null);
    await tester.pump();
    final field = ((presented.single['sections'] as List).single['rows'] as List).single as Map;
    expect(field['value'], 'What about this?');
    expect(field['maximumLength'], 10000);
    expect(harness.quoted, ['about this']);
  });

  testWidgets('Ask Omi cancelled quotes nothing', (tester) async {
    NativeTestHost.install();
    final harness = await pump(tester, [_human('h1', 'Hello'), _ai('a1')]);
    final presented = _present((_) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'});
    await harness.row('chat_actions_a1_0').action!('ask');
    await tester.pumpAndSettle();
    expect(presented, hasLength(1));
    expect(find.byType(SelectionArea), findsNothing, reason: 'a cancellation is not sent to the Flutter path');
    expect(harness.quoted, isEmpty);
  });

  testWidgets('Helpful toggles 1 to 0 and reverts when the owner refuses', (tester) async {
    final message = _ai('a1')..rating = 1;
    final harness = await pump(tester, [_human('h1', 'Hi'), message]);
    expect(harness.row('chat_actions_a1_0').subtitle, _l10n.helpful);
    expect(harness.row('chat_actions_a1_0').options.keys, ['copy', 'helpful', 'not_helpful', 'share', 'ask']);

    harness.rated = false;
    await dispatch(harness, 'chat_actions_a1_0', 'helpful');
    await tester.pump();
    expect(harness.ratings, [(0, null)]);
    expect(harness.row('chat_actions_a1_0').subtitle, _l10n.helpful, reason: 'a refused rating reverts');

    harness.rated = true;
    await dispatch(harness, 'chat_actions_a1_0', 'helpful');
    await tester.pump();
    expect(harness.ratings.last, (0, null));
    expect(harness.row('chat_actions_a1_0').subtitle, '');
    expect(message.rating, isNull);
  });

  testWidgets('Not Helpful when already chosen clears back to 0', (tester) async {
    final message = _ai('a1')..rating = -1;
    final harness = await pump(tester, [_human('h1', 'Hi'), message]);
    await dispatch(harness, 'chat_actions_a1_0', 'not_helpful');
    await tester.pump();
    expect(harness.ratings, [(0, null)]);
  });

  testWidgets('Not Helpful asks why first: Close rates nothing, Submit rates with the reason', (tester) async {
    final harness = await pump(tester, [_human('h1', 'Hi'), _ai('a1')]);
    unawaited(dispatch(harness, 'chat_actions_a1_0', 'not_helpful'));
    await tester.pumpAndSettle();
    expect(find.byType(FeedbackBottomSheet), findsOneWidget);
    // Closing the sheet without Submit.
    Navigator.of(tester.element(find.byType(FeedbackBottomSheet))).pop();
    await tester.pumpAndSettle();
    expect(harness.ratings, isEmpty);
    expect(harness.row('chat_actions_a1_0').subtitle, '');

    unawaited(dispatch(harness, 'chat_actions_a1_0', 'not_helpful'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(_l10n.feedbackReasonTooVerbose));
    await tester.enterText(find.byType(TextField), 'too long');
    await tester.tap(find.text(_l10n.submit));
    await tester.pumpAndSettle();
    expect(harness.ratings, [(-1, 'too_verbose: too long')]);
    expect(harness.row('chat_actions_a1_0').subtitle, _l10n.notHelpful);
  });

  testWidgets('a day summary projects its header, numbered list, copy/share menu and review rows', (tester) async {
    final summary = ServerMessage.fromJson({
      'id': 'd1',
      'created_at': '2026-09-02T12:00:00Z',
      'text': 'You shipped. You rested',
      'sender': 'ai',
      'type': 'day_summary',
      'content_blocks': [
        {
          'type': 'memoryReviewCard',
          'id': 'summary-1:memories',
          'summaryId': 'summary-1',
          'date': '2026-09-01',
          'items': [
            {'memoryId': 'mem-1', 'content': 'Prefers async standups', 'category': 'work'},
          ],
        },
      ],
    });
    final harness = await pump(tester, [_human('h1', 'Hi'), summary]);
    expect(harness.row('chat_daysummary_d1_0').kind, 'label');
    expect(harness.row('chat_daysummary_d1_1').blocks.map((block) => block['prefix']), ['1.', '2.']);
    expect(harness.row('chat_actions_d1_0').options.keys, ['copy', 'share']);
    expect(harness.row('chat_reviewtitle_d1_0').title, _l10n.memoryReviewTitle);
    expect(harness.row('chat_review_d1_0').kind, 'menu');
    expect(harness.rows.any((row) => row.id.contains('mem-1')), isFalse);
    expect(harness.rows.every((row) => row.valid), isTrue);
  });

  testWidgets('copy and share report the message length only', (tester) async {
    AnalyticsManager.resetForTesting();
    addTearDown(AnalyticsManager.resetForTesting);
    final analytics = _Analytics();
    AnalyticsManager.configure(analytics);
    _mockPackageInfo();
    await tester.runAsync(AnalyticsManager.init);
    // The OS confirmation path; the copy itself still runs through OmiClipboard.
    OmiClipboard.debugSystemConfirmsCopy = true;
    addTearDown(() => OmiClipboard.debugSystemConfirmsCopy = null);
    _messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
    _messenger.setMockMethodCallHandler(const MethodChannel('dev.fluttercommunity.plus/share'),
        (call) async => 'dev.fluttercommunity.plus/share/success');
    addTearDown(() {
      _messenger.setMockMethodCallHandler(SystemChannels.platform, null);
      _messenger.setMockMethodCallHandler(const MethodChannel('dev.fluttercommunity.plus/share'), null);
    });
    final harness = await pump(tester, [_human('h1', 'Hi'), _ai('a1', text: 'Secret plan')]);
    analytics.events.clear();
    await dispatch(harness, 'chat_actions_a1_0', 'copy');
    await dispatch(harness, 'chat_actions_a1_0', 'share');
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    final chat = analytics.events.where((event) => event.key.startsWith('Chat Message')).toList();
    expect(chat.map((event) => event.key), ['Chat Message Copied', 'Chat Message Shared']);
    for (final event in chat) {
      expect(event.value['message_length'], 'Secret plan'.length);
      expect(event.value.values.whereType<String>().any((value) => value.contains('Secret')), isFalse);
    }
    expect(harness.ratings, isEmpty, reason: 'copy and share never rate');
  });

  testWidgets('a task toggles once through the tasks owner, and a bool is refused while unresolved', (tester) async {
    final tasks = _Tasks([_task('task-1')])..pending = Completer<void>();
    final harness = await pump(
        tester,
        [
          _human('h1', 'Hi'),
          _ai('a1', text: '', blocks: [
            {'id': 'b-task', 'type': 'taskCard', 'taskId': 'task-1'},
            {'id': 'b-missing', 'type': 'taskCard', 'taskId': 'task-2'},
          ]),
        ],
        tasks: tasks);
    await tester.pump();
    // The provider's own constructor preload is the only load so far.
    final preload = tasks.loads;
    await tester.pump(const Duration(seconds: 1));
    expect(tasks.loads, preload, reason: 'history alone never loads tasks; Swift showing a card does');
    expect(harness.row('chat_task_a1_1').subtitle, _l10n.loading);
    await dispatch(harness, '_visible:chat_task_a1_1', null);
    await dispatch(harness, '_visible:chat_task_a1_0', null);
    await tester.pump();
    expect(tasks.loads, preload + 1, reason: 'once per message');
    expect(harness.row('chat_task_a1_0').kind, 'task');
    expect(harness.row('chat_task_a1_0').value, false);
    final first = dispatch(harness, 'chat_task_a1_0', true);
    final second = dispatch(harness, 'chat_task_a1_0', true);
    tasks.pending!.complete();
    await Future.wait([first, second]);
    expect(tasks.updates, [('task-1', true)]);

    final missing = harness.row('chat_task_a1_1');
    expect(missing.kind, 'label');
    expect(missing.subtitle, _l10n.chatBlockUnavailable);
    await expectLater(dispatch(harness, 'chat_task_a1_1', true), throwsA(isA<PlatformException>()));
    expect(tasks.updates, hasLength(1));
  });

  testWidgets('a question option sends its prepared answer; an answered card shows only its choice', (tester) async {
    Map<String, dynamic> question({String? selected}) => {
          'id': 'b-question',
          'type': 'questionCard',
          'questionId': 'question-1',
          'text': 'Which first?',
          'subject': {'kind': 'goal', 'id': 'goal-1'},
          'options': [
            {'optionId': 'ship', 'label': 'Ship it', 'preparedAnswer': 'Ship it today'},
            {'optionId': 'later', 'label': 'Later', 'preparedAnswer': 'Remind me tomorrow'},
          ],
          if (selected != null) 'selectedOptionId': selected,
        };
    final harness = await pump(tester, [
      _human('h1', 'Hi'),
      _ai('a1', text: 'Pick one.', blocks: [question()]),
      _ai('a2', text: 'Pick one.', blocks: [question(selected: 'later')]),
    ]);
    await dispatch(harness, 'chat_answer_a1_0', null);
    expect(harness.sent, ['Ship it today']);
    expect(harness.rows.where((row) => row.id.startsWith('chat_answer_a2_')).map((row) => (row.title, row.enabled)),
        [('Later', false)]);
  });

  testWidgets('a conversation link that is gone flips to unavailable', (tester) async {
    NativeTestHost.installOwner();
    final harness = await pump(tester, [
      _human('h1', 'Hi'),
      _ai('a1', text: '', blocks: [
        {'id': 'b-link', 'type': 'conversationLink', 'conversationId': 'gone', 'summary': 'Planning'},
      ]),
    ]);
    harness.fetched = () => null;
    expect(harness.row('chat_link_a1_0').kind, 'navigation');
    await dispatch(harness, 'chat_link_a1_0', null);
    await tester.pump();
    expect(harness.row('chat_link_a1_0').kind, 'label');
    expect(harness.row('chat_link_a1_0').subtitle, _l10n.chatBlockUnavailable);
  });

  testWidgets('a session change while a link resolves navigates nowhere and changes nothing', (tester) async {
    NativeTestHost.installOwner();
    final harness = await pump(tester, [
      _human('h1', 'Hi'),
      _ai('a1', text: '', blocks: [
        {'id': 'b-link', 'type': 'captureLink', 'conversationId': 'c-1', 'summary': 'Standup'},
      ]),
    ]);
    harness.fetching = Completer();
    final open = dispatch(harness, 'chat_link_a1_0', null);
    await tester.pump();
    expect(harness.row('chat_link_a1_0').enabled, isFalse, reason: 'one open at a time');
    AuthService.installLocalHarnessTokenGateway(const _AnotherOwner());
    harness.fetching!.complete(
        ServerConversation(id: 'c-1', createdAt: DateTime.utc(2026, 9, 1), structured: Structured('Standup', 'Notes')));
    await open;
    await tester.pumpAndSettle();
    expect(find.byType(ConversationDetailPage), findsNothing);
    expect(harness.row('chat_link_a1_0').kind, 'navigation');
  });

  testWidgets('activity steps and charts render inline', (tester) async {
    final streaming = _ai('a1', text: '')..thinkings = ['Searching memories', 'Making a chart'];
    final provider = MessageProvider()
      ..messages = [_human('h1', 'Hi'), streaming]
      ..showTypingIndicator = true;
    var harness = await pump(tester, provider.messages, provider: provider);
    expect(harness.rows.where((row) => row.id.startsWith('chat_activity_a1_')).map((row) => (row.kind, row.title)),
        [('navigation', 'Searching memories'), ('navigation', 'Making a chart')]);
    expect(harness.row('chat_activity_a1_0').symbol, 'lightbulb');
    expect(harness.row('chat_chart_a1_0').title, _l10n.loading);
    expect(harness.row('chat_chart_a1_0').symbol, 'chart.bar');

    final done = _ai('a1', text: 'Your week.')
      ..thinkings = ['Searching memories', 'Making a chart']
      ..chartData = ChartData('bar', 'Steps', [
        ChartDataset('Steps', [ChartDataPoint('Monday ${'x' * 80}', 3), ChartDataPoint('Tue', 5)])
      ]);
    harness = await pump(tester, [_human('h1', 'Hi'), done]);
    final activity = harness.row('chat_activity_a1_0');
    expect((activity.kind, activity.title, activity.subtitle), ('navigation', 'Making a chart', _l10n.activity));
    final chart = harness.row('chat_chart_a1_0');
    expect(chart.chartStyle, 'bar');
    expect(chart.points.map((point) => point['x']), [0, 1]);
    expect((chart.points.first['label'] as String).characters.length, 64);
    expect(chart.valid, isTrue);

    final empty = _ai('a2', text: 'Nothing to plot.')..chartData = ChartData('line', 'Empty', []);
    harness = await pump(tester, [_human('h1', 'Hi'), empty]);
    expect(harness.rows.any((row) => row.id.startsWith('chat_chart_')), isFalse);
  });

  testWidgets('evidence leaves out conversation sources the citations already list', (tester) async {
    final message = ServerMessage.fromJson({
      'id': 'a1',
      'created_at': '2026-09-02T12:00:00Z',
      'text': 'You met twice.',
      'sender': 'ai',
      'type': 'text',
      'memories': [
        {
          'id': 'conversation-1',
          'created_at': '2026-09-01T10:00:00Z',
          'structured': {'title': 'Standup', 'emoji': '🗓'},
        },
      ],
      'evidence': {
        'schema_version': 1,
        'request_id': 'request-1',
        'references': [
          {'id': 'r1', 'kind': 'conversation_summary', 'state': 'available', 'conversation_id': 'conversation-1'},
          {'id': 'r2', 'kind': 'screen', 'state': 'pruned', 'frame_id': 'frame-1', 'title': 'Editor'},
        ],
      },
    });
    final harness = await pump(tester, [_human('h1', 'Hi'), message]);
    final evidence = harness.rows.where((row) => row.id.startsWith('chat_evidence_')).toList();
    expect(
        evidence.map((row) => (row.id, row.title, row.symbol)), [('chat_evidence_a1_0', 'Editor', 'desktopcomputer')]);
    expect(evidence.single.action, isNull, reason: 'evidence has no navigator yet');
    expect(harness.row('chat_citation_a1_0').kind, 'navigation');
    expect(harness.row('chat_citation_a1_0').title, contains('Standup'));
  });

  testWidgets('attachments are labels with a symbol by extension, only once uploaded', (tester) async {
    expect(
      ['a.pdf', 'notes.txt', 'readme.md', 'brief.doc', 'sheet.xlsx', 'deck.pptx', 'archive.zip'].map(chatFileSymbol),
      [
        'doc.richtext',
        'doc.plaintext',
        'doc.plaintext',
        'doc.text',
        'tablecells',
        'rectangle.on.rectangle.angled',
        'doc'
      ],
    );
    MessageFile file(String name) =>
        MessageFile('openai', null, name, 'application/pdf', 'f-$name', DateTime(2026), null);
    final uploaded = _human('h1', 'See attached')
      ..files = [file('a.pdf')]
      ..filesId = ['f-a.pdf'];
    final pending = _human('h2', 'Again')..files = [file('b.pdf')];
    final harness = await pump(tester, [uploaded, pending]);
    expect(harness.row('chat_file_h1_0').symbol, 'doc.richtext');
    expect(harness.row('chat_file_h1_0').kind, 'label');
    expect(harness.rows.any((row) => row.id.startsWith('chat_file_h2_')), isFalse);
  });

  group('ChatPage', () {
    Future<(NativeTestHost, MessageProvider)> pumpPage(WidgetTester tester) async {
      _mockPackageInfo();
      final host = NativeTestHost.install();
      final provider = _PageMessages()
        ..messages = [
          _human('h1', 'Plan my week'),
          _ai('a1', text: '## Week\n\n- **Ship** it', blocks: [
            {'id': 'b-task', 'type': 'taskCard', 'taskId': 'task-1'},
          ])
            ..chartData = ChartData('line', 'Steps', [
              ChartDataset('Steps', [ChartDataPoint('Mon', 3), ChartDataPoint('Tue', 5)])
            ]),
        ]
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          throw Exception('socket closed');
        };
      provider.addMessageLocally('hello');
      await provider.sendMessageStreamToServer('hello');
      final memories = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            const GetMemoriesResult([], true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: true),
      );
      addTearDown(memories.dispose);
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<MessageProvider>.value(value: provider),
          ChangeNotifierProvider<ActionItemsProvider>.value(value: _Tasks([_task('task-1')])),
          ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
          ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
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
                  )),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: [Locale('en')],
          home: ChatPage(),
        ),
      ));
      await NativeTestHost.settle(tester);
      return (host, provider);
    }

    List<NativeRow> pageRows(WidgetTester tester) =>
        IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface)));

    /// The row ids of the last snapshot the page published to the native view.
    List<String> published(NativeTestHost host, int view) {
      final update = host.calls.lastWhere((call) => call.$1 == view && call.$2.method == 'update').$2;
      return [
        for (final section in (update.arguments as Map)['sections'] as List)
          for (final row in (section as Map)['rows'] as List) (row as Map)['id'] as String,
      ];
    }

    testWidgets('structured replies stay native: the page publishes them instead of its fallback', (tester) async {
      final (host, provider) = await pumpPage(tester);
      final failed = provider.messages.last;
      expect(provider.isReplyFailed(failed), isTrue);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(find.byType(ChatHeader), findsNothing, reason: 'the classic chat is not mounted');
      final view = host.created.single;
      final ids = published(host, view);
      expect(ids.toSet(), hasLength(ids.length), reason: 'transcript rows and page rows share one id space');
      expect(
          ids,
          containsAll([
            'chat_message_h1',
            'chat_message_a1',
            'chat_task_a1_0',
            'chat_chart_a1_0',
            'chat_actions_a1_0',
            'chat_message_${failed.id}',
          ]));
      expect(pageRows(tester).singleWhere((row) => row.id == 'chat_message_${failed.id}').symbol, 'arrow.clockwise');
      expect(ids.contains('chat_context'), isFalse);
    });

    testWidgets('Ask Omi from the actions menu quotes the trimmed text as the next context', (tester) async {
      final (host, _) = await pumpPage(tester);
      _present((_) => {
            'action': 'ask',
            'values': {'chat_ask_text': '  Ship it  '},
            'reason': 'action',
          });
      final view = host.created.single;
      await host.sendFromNative(view, const MethodCall('action', {'id': 'chat_actions_a1_0', 'value': 'ask'}));
      await NativeTestHost.settle(tester);
      expect(pageRows(tester).singleWhere((row) => row.id == 'chat_context').title, 'Ship it');
      expect(published(host, view), contains('chat_context'));
      expect(host.disposed, isEmpty, reason: 'the chat never fell back to Flutter');
    });
  });

  group('What went wrong?', () {
    Future<(List<(String, String?)>, int)> pumpSheet(WidgetTester tester) async {
      final host = NativeTestHost.install();
      final submitted = <(String, String?)>[];
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => FeedbackBottomSheet(native: true, onSubmit: (r, c) => submitted.add((r, c))))),
            child: const Text('open'),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      return (submitted, host.created.single);
    }

    Future<Object?> send(WidgetTester tester, int view, String id, Object? value) async {
      final reply = await _sendFromNative(view, MethodCall('action', {'id': id, 'value': value}));
      await tester.pump();
      return reply;
    }

    testWidgets('Submit stays disabled until a reason, and reports the reason and comment', (tester) async {
      final (submitted, view) = await pumpSheet(tester);
      NativeRow row(String id) =>
          IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface)))
              .singleWhere((row) => row.id == id);
      expect(row('feedback_submit').enabled, isFalse);
      expect(row('feedback_reason_too_verbose').symbol, 'circle');
      expect(await send(tester, view, 'feedback_submit', null), isA<PlatformException>());
      expect(submitted, isEmpty);

      await send(tester, view, 'feedback_reason_too_verbose', null);
      expect(row('feedback_reason_too_verbose').symbol, 'checkmark.circle.fill');
      expect(row('feedback_comment_text').maximumLength, 500);
      expect(await send(tester, view, 'feedback_comment_text', 'x' * 501), isA<PlatformException>());
      await send(tester, view, 'feedback_comment_text', '  too long  ');
      await send(tester, view, 'feedback_submit', null);
      await tester.pumpAndSettle();
      expect(submitted, [('too_verbose', 'too long')]);
      expect(find.byType(FeedbackBottomSheet), findsNothing);
    });

    testWidgets('Close submits nothing', (tester) async {
      final (submitted, view) = await pumpSheet(tester);
      await send(tester, view, 'feedback_reason_other', null);
      await send(tester, view, 'feedback_close', null);
      await tester.pumpAndSettle();
      expect(submitted, isEmpty);
      expect(find.byType(FeedbackBottomSheet), findsNothing);
    });
  });
}

/// Delivers a native command to the mocked surface channel; answers the error a refusal reports.
Future<Object?> _sendFromNative(int view, MethodCall call) async {
  final channel = MethodChannel('com.omi.native_ui/surface/$view');
  ByteData? reply;
  await _messenger.handlePlatformMessage(channel.name, channel.codec.encodeMethodCall(call), (data) => reply = data);
  try {
    return channel.codec.decodeEnvelope(reply!);
  } on PlatformException catch (error) {
    return error;
  }
}

void _mockPackageInfo() {
  const channel = MethodChannel('dev.fluttercommunity.plus/package_info');
  _messenger.setMockMethodCallHandler(channel,
      (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'});
  addTearDown(() => _messenger.setMockMethodCallHandler(channel, null));
}
