import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _conversation(String title, {ConversationStatus status = ConversationStatus.completed}) =>
    ServerConversation(
      id: 'title-refresh',
      createdAt: DateTime(2026, 11, 18, 20, 39),
      structured: Structured(title, title.isEmpty ? '' : 'Overview', emoji: '🎉'),
      status: status,
    );

ConversationDetailProvider _opened(ServerConversation opened, ServerConversation stored) =>
    ConversationDetailProvider(fetchConversation: (_) async => stored)
      ..selectedDate = conversationLocalDayKey(opened.createdAt)
      ..setCachedConversation(opened)
      ..titleController = TextEditingController(text: opened.structured.title)
      ..titleFocusNode = FocusNode();

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  // Finish opens the page before the summary is stored, so its title lands on a refresh.
  test('a title stored after the page opened replaces the empty one', () async {
    final detail = _opened(_conversation('', status: ConversationStatus.processing), _conversation('Launch Plan'));
    expect(await detail.refreshConversation(), isTrue);
    expect(detail.titleController!.text, 'Launch Plan');
  });

  test('a title the user already changed is kept', () async {
    final detail = _opened(_conversation('', status: ConversationStatus.processing), _conversation('Launch Plan'));
    detail.titleController!.text = 'My own title';
    await detail.refreshConversation();
    expect(detail.titleController!.text, 'My own title');
  });

  testWidgets('a field being edited is not overwritten', (tester) async {
    final detail = _opened(_conversation('', status: ConversationStatus.processing), _conversation('Launch Plan'));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: TextField(controller: detail.titleController, focusNode: detail.titleFocusNode)),
    ));
    detail.titleFocusNode!.requestFocus();
    await tester.pump();
    expect(await tester.runAsync(detail.refreshConversation), isTrue, reason: "the stored title did land");
    expect(detail.titleController!.text, isEmpty);
  });

  // Home's list read can store the title first; the page then never refreshes on its own.
  test('a title that arrives through the conversation list fills the empty field', () async {
    final opened = _conversation('', status: ConversationStatus.processing);
    final stored = _conversation('Launch Plan');
    final list = ConversationProvider(isSignedIn: () => false)
      ..conversations = [stored]
      ..groupedConversations = {
        conversationLocalDayKey(stored.createdAt): [stored],
      };
    final apps = AppProvider();
    final detail = _opened(opened, stored);
    addTearDown(() {
      detail.dispose();
      list.dispose();
      apps.dispose();
    });
    detail.setProviders(apps, list);
    await Future<void>.delayed(Duration.zero);
    expect(detail.titleController!.text, 'Launch Plan');
  });
}
