import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/conversation_provider.dart';
import '../support/spine/contract.dart';
import '../support/spine/widgets.dart';
import 'c3_fixture.dart';

ServerConversation seed(String id) => ServerConversation(
    id: id,
    createdAt: DateTime.utc(2026, 9, 17),
    structured: Structured('Synthetic $id', 'Fixture overview', emoji: '', category: 'other'));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractWidgets('C3 fixture outage renders error, retry recovers, valid empty alone renders empty', (tester) async {
    pendingContract('C3');
    final fixture = await tester.runAsync(C3Fixture.start);
    addTearDown(fixture!.close);
    fixture.backend.failNext('GET', '/v1/conversations', status: 503);
    final p = composeTypedConversationProvider(ConversationApi(baseUrl: fixture.backend.baseUrl, send: fixture.send));
    expect(p.runtimeType, ConversationProvider);
    addTearDown(p.dispose);
    await tester.runAsync(() async => await p.forceRefreshConversations());
    expect(fixture.backend.countOf('GET', '/v1/conversations'), 1);
    expect(p.apiViewState.phase, ApiViewPhase.error);
    expect(p.isLoadingConversations, isFalse);
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: ConversationApiStatus(provider: p))));
    await tester.pump();
    expect(find.byKey(const ValueKey('omi.conversations.error')), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.conversations.empty')), findsNothing);
    final semantics = tester.ensureSemantics();
    final errorNode = tester.getSemantics(find.byKey(const ValueKey('omi.conversations.error')));
    expect(errorNode.label.trim(), isNotEmpty);
    semantics.dispose();
    await tester.runAsync(() async => await p.forceRefreshConversations());
    await tester.pump();
    expect(p.apiViewState.phase, ApiViewPhase.empty);
    expect(find.byKey(const ValueKey('omi.conversations.error')), findsNothing);
    expect(find.byKey(const ValueKey('omi.conversations.empty')), findsOneWidget);
    expect(fixture.backend.countOf('GET', '/v1/conversations'), 2);
  });

  for (final status in [402, 422]) {
    contractWidgets('C3 detail $status leaves Processing and does not retry on timer ticks', (tester) async {
      pendingContract('C3');
      final fixture = await tester.runAsync(C3Fixture.start);
      addTearDown(fixture!.close);
      fixture.backend.failNext('GET', '/v1/conversations/one', status: status);
      final p = composeTypedConversationProvider(ConversationApi(baseUrl: fixture.backend.baseUrl, send: fixture.send));
      expect(p.runtimeType, ConversationProvider);
      addTearDown(p.dispose);
      final conversation = seed('one');
      p.conversations = [conversation];
      p.processingConversations = [conversation];
      await tester.runAsync(() => p.refreshTypedDetail('one'));
      final state = p.typedDetailState('one');
      expect(state.phase, status == 402 ? ApiViewPhase.locked : ApiViewPhase.terminal);
      expect(state.problem!.kind, status == 402 ? ApiProblemKind.paymentRequired : ApiProblemKind.unprocessable);
      expect(p.processingConversations.where((c) => c.id == 'one'), isEmpty);
      expect(p.conversations.map((c) => c.id), contains('one'));
      await tester.pump(const Duration(minutes: 2));
      expect(fixture.backend.countOf('GET', '/v1/conversations/one'), 1);
      expect(p.isLoadingConversations, isFalse);
    });
  }
  contractTest('C3 conversation parser keeps exact valid records around a malformed row', () async {
    pendingContract('C3');
    final fixture = await C3Fixture.start();
    addTearDown(fixture.close);
    fixture.backend.conversations.addAll([
      seed('first').toJson(),
      {'id': 42},
      seed('last').toJson()
    ]);
    final result = await ConversationApi(baseUrl: fixture.backend.baseUrl, send: fixture.send).list();
    final success = result as ApiSuccess<List<ServerConversation>>;
    expect(success.data.map((c) => c.id), ['first', 'last']);
    expect(success.data.map((c) => c.structured.title), ['Synthetic first', 'Synthetic last']);
    expect(success.rejectedRows, 1);
    expect(fixture.backend.countOf('GET', '/v1/conversations'), 1);
    final missing = await ConversationApi(baseUrl: fixture.backend.baseUrl, send: fixture.send).byId('missing');
    expect((missing as ApiFailure<ServerConversation>).problem.kind, ApiProblemKind.notFound);
  });
  contractTest('C3 static adoption tripwire: production list page uses the tested status region', () {
    pendingContract('C3');
    final source = File('lib/pages/conversations/conversations_page.dart').readAsStringSync();
    // Static wiring tripwire, not claimed as behavioral UI coverage.
    final code = source.replaceAll(RegExp(r'//[^\n]*|/\*[\s\S]*?\*/'), '');
    expect(code, matches(RegExp(r'\bConversationApiStatus\s*\(')));
  });
}
