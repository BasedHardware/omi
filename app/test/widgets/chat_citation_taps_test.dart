import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/jump_to_latest_button.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/components/chat_evidence_card.dart';

void main() {
  ServerMessage messageWithMemories({int memoryCount = 3, ChatEvidenceReferenceEnvelope? evidence}) {
    final createdAt = DateTime.parse('2026-08-23T12:00:00Z');
    final memories = List<MessageConversation>.generate(
      memoryCount,
      (index) =>
          MessageConversation('convo-$index', createdAt, MessageConversationStructured('Conversation $index', '🧠')),
    );
    return ServerMessage(
      'ai-1',
      createdAt,
      'You talked about shipping the citation fix.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      const [],
      const [],
      memories,
      evidenceEnvelope: evidence,
    );
  }

  Future<void> pumpCitations(
    WidgetTester tester, {
    required ServerMessage message,
    Future<ServerConversation?> Function(String id)? fetchConversation,
    ConversationProvider? conversations,
  }) async {
    final ownedProvider = conversations == null;
    final conversationProvider = conversations ?? ConversationProvider(isSignedIn: () => false);
    if (ownedProvider) {
      addTearDown(conversationProvider.dispose);
    }

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
            body: SingleChildScrollView(
              child: AIMessage(
                message: message,
                sendMessage: (_) {},
                displayOptions: false,
                updateConversation: (_) {},
                setMessageNps: (int value, {String? reason}) {},
                fetchConversation: fetchConversation,
              ),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('citation GestureDetectors are not wrapped by SelectionArea', (tester) async {
    await pumpCitations(tester, message: messageWithMemories());

    final citation = find.byKey(const ValueKey('chat-citation-convo-0'));
    expect(citation, findsOneWidget);
    expect(find.ancestor(of: citation, matching: find.byType(SelectionArea)), findsNothing);
    expect(find.ancestor(of: find.byType(MarkdownBody), matching: find.byType(SelectionArea)), findsOneWidget);
  });

  testWidgets('a memories message renders one source list and all attached citations', (tester) async {
    const evidence = ChatEvidenceReferenceEnvelope(
      references: [
        ChatEvidenceReference(
          id: 'summary-0',
          kind: ChatEvidenceReferenceKind.conversationSummary,
          state: ChatEvidenceReferenceState.available,
          conversationId: 'convo-0',
          title: 'Conversation 0',
          summary: 'Standup overview that must not duplicate the citation pills.',
        ),
        ChatEvidenceReference(
          id: 'summary-1',
          kind: ChatEvidenceReferenceKind.conversationSummary,
          state: ChatEvidenceReferenceState.available,
          conversationId: 'convo-1',
          title: 'Conversation 1',
          summary: 'Another dead overview card.',
        ),
      ],
    );

    await pumpCitations(tester, message: messageWithMemories(memoryCount: 5, evidence: evidence));

    expect(find.byKey(const ValueKey('chat-citation-list')), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-evidence-reference-list')), findsNothing);
    expect(find.byType(ChatEvidenceReferenceCard), findsNothing);
    for (var index = 0; index < 5; index++) {
      expect(find.byKey(ValueKey('chat-citation-convo-$index')), findsOneWidget);
      expect(find.textContaining('Conversation $index'), findsOneWidget);
    }
  });

  testWidgets('citation tap fetches by id on a local miss and surfaces failure', (tester) async {
    final fetchedIds = <String>[];
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);

    await pumpCitations(
      tester,
      message: messageWithMemories(memoryCount: 1),
      conversations: conversations,
      fetchConversation: (id) async {
        fetchedIds.add(id);
        return null;
      },
    );

    await tester.tap(find.byKey(const ValueKey('chat-citation-convo-0')));
    await tester.pumpAndSettle();

    expect(fetchedIds, ['convo-0']);
    expect(find.text('Conversation not found or has been deleted'), findsOneWidget);
  });

  test('resolveChatCitationConversation fetches when the grouped map misses', () async {
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);

    var fetched = false;
    final fetchedConversation = ServerConversation(
      id: 'remote-1',
      createdAt: DateTime.parse('2026-08-23T12:00:00Z'),
      structured: Structured('Remote', 'Overview', emoji: '🧠'),
    );

    final resolved = await resolveChatCitationConversation(
      conversations: conversations,
      conversationId: 'remote-1',
      fetchConversation: (id) async {
        fetched = true;
        expect(id, 'remote-1');
        return fetchedConversation;
      },
    );

    expect(fetched, isTrue);
    expect(resolved, same(fetchedConversation));
  });

  test('resolveChatCitationConversation uses the local group and skips the fetch', () async {
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);
    final local = ServerConversation(
      id: 'local-1',
      createdAt: DateTime.parse('2026-08-23T12:00:00Z'),
      structured: Structured('Local', 'Overview', emoji: '🧠'),
    );
    conversations.conversations = [local];
    conversations.groupedConversations = {
      conversationLocalDayKey(local.createdAt): [local],
    };

    var fetched = false;
    final resolved = await resolveChatCitationConversation(
      conversations: conversations,
      conversationId: 'local-1',
      fetchConversation: (_) async {
        fetched = true;
        return null;
      },
    );

    expect(fetched, isFalse);
    expect(resolved, same(local));
  });

  testWidgets('Latest chip does not absorb taps beside itself', (tester) async {
    var behindTapped = false;
    var chipTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox(
          width: 400,
          height: 400,
          child: Stack(
            alignment: Alignment.bottomCenter,
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onTap: () => behindTapped = true,
                  behavior: HitTestBehavior.opaque,
                  child: const ColoredBox(color: Color(0xFF111111)),
                ),
              ),
              ChatJumpToLatestButton(label: 'Latest', onTap: () => chipTapped = true),
            ],
          ),
        ),
      ),
    );

    await tester.tapAt(const Offset(24, 372));
    expect(behindTapped, isTrue);
    expect(chipTapped, isFalse);

    await tester.tap(find.text('Latest'));
    expect(chipTapped, isTrue);
  });
}
