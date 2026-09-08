import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/chat_scroll_policy.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  ServerMessage messageWithMemories({int memoryCount = 5}) {
    final createdAt = DateTime.parse('2026-08-23T12:00:00Z');
    final memories = List<MessageConversation>.generate(
      memoryCount,
      (index) => MessageConversation(
        'convo-$index',
        createdAt,
        MessageConversationStructured('Conversation $index', '🧠'),
      ),
    );
    return ServerMessage(
      'ai-1',
      createdAt,
      'You talked about shipping the citation fix. What is up.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      const [],
      const [],
      memories,
    );
  }

  test(
    'continued drag while already free-scrolling does not request a rebuild',
    () {
      expect(
        ChatScrollPolicy.nextMode(
          current: ChatScrollMode.freeScrolling,
          isUserOrDragScroll: true,
          atLiveEdge: false,
        ),
        isNull,
      );
    },
  );

  test('first user drag while following requests free-scrolling once', () {
    expect(
      ChatScrollPolicy.nextMode(
        current: ChatScrollMode.followingBottom,
        isUserOrDragScroll: true,
        atLiveEdge: false,
      ),
      ChatScrollMode.freeScrolling,
    );
  });

  test('transcript bottom padding does not depend on scroll mode', () {
    expect(ChatScrollPolicy.transcriptBottomPadding, 72);
  });

  testWidgets('a drag while following rebuilds the transcript at most once', (
    tester,
  ) async {
    final rebuilds = <int>[];
    await tester.pumpWidget(
      MaterialApp(
        home: _ScrollHost(
          onRebuild: () => rebuilds.add(1),
          child: ListView(
            children: List.generate(
              30,
              (i) => SizedBox(height: 80, child: Text('row $i')),
            ),
          ),
        ),
      ),
    );

    await tester.drag(find.byType(ListView), const Offset(0, -120));
    await tester.pump();

    expect(rebuilds.length, lessThanOrEqualTo(1));
  });

  testWidgets(
    'citation titles and heights survive a ListView drag under keyboard inset',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      tester.view.viewInsets = const FakeViewPadding(bottom: 336);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewInsets);

      final conversationProvider = ConversationProvider(
        isSignedIn: () => false,
      );
      addTearDown(conversationProvider.dispose);
      final message = messageWithMemories();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: conversationProvider),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ],
          child: MaterialApp(
            theme: ThemeData.dark(),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(
              body: _ScrollHost(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(
                    18,
                    16,
                    18,
                    ChatScrollPolicy.transcriptBottomPadding,
                  ),
                  itemCount: 4,
                  itemBuilder: (context, index) {
                    return Padding(
                      key: ValueKey('msg-$index'),
                      padding: const EdgeInsets.only(top: 16),
                      child: AIMessage(
                        message: message,
                        sendMessage: (_) {},
                        displayOptions: false,
                        updateConversation: (_) {},
                        setMessageNps: (int value, {String? reason}) {},
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      final citation = find.byKey(const ValueKey('chat-citation-convo-0')).first;
      expect(citation, findsOneWidget);
      final before = tester.getSize(citation);
      expect(before.height, greaterThanOrEqualTo(40));
      expect(find.textContaining('Conversation 0'), findsWidgets);
      expect(find.textContaining('What is up'), findsWidgets);

      await tester.drag(find.byType(ListView), const Offset(0, -24));
      await tester.pump();

      expect(find.byKey(const ValueKey('chat-citation-convo-0')), findsWidgets);
      final after = tester.getSize(
        find.byKey(const ValueKey('chat-citation-convo-0')).first,
      );
      expect(after.height, greaterThanOrEqualTo(40));
      expect(after.height, closeTo(before.height, 1));
      expect(find.textContaining('Conversation 0'), findsWidgets);
      expect(find.textContaining('What is up'), findsWidgets);
    },
  );
}

class _ScrollHost extends StatefulWidget {
  const _ScrollHost({required this.child, this.onRebuild});

  final Widget child;
  final VoidCallback? onRebuild;

  @override
  State<_ScrollHost> createState() => _ScrollHostState();
}

class _ScrollHostState extends State<_ScrollHost> {
  ChatScrollMode _mode = ChatScrollMode.followingBottom;

  bool _onNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    final isUserScroll = notification is UserScrollNotification && notification.direction != ScrollDirection.idle;
    final isDragScroll = notification is ScrollUpdateNotification && notification.dragDetails != null;
    final next = ChatScrollPolicy.nextMode(
      current: _mode,
      isUserOrDragScroll: isUserScroll || isDragScroll,
      atLiveEdge: ChatScrollPolicy.atLiveEdge(notification.metrics),
    );
    if (next == null) return false;
    setState(() {
      _mode = next;
      widget.onRebuild?.call();
    });
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollNotification>(
      onNotification: _onNotification,
      child: widget.child,
    );
  }
}
