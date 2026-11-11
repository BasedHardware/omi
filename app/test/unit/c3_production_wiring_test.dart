import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

import '../spine/c3_fixture.dart';
import '../support/typed_conversation_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('createProductionConversationProvider always attaches ConversationApi', () {
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    final provider = createProductionConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    expect(provider, isA<ConversationProvider>());
    expect(provider.usesTypedConversationApi, isTrue);
  });

  test('main.dart boots ConversationProvider through createProductionConversationProvider', () {
    final source = File('lib/main.dart').readAsStringSync();
    expect(source.contains('createProductionConversationProvider()'), isTrue);
    expect(source.contains('create: (context) => ConversationProvider()'), isFalse);
  });

  testWidgets('production conversation provider renders 503 as error, not an empty account', (tester) async {
    final fixture = await tester.runAsync(C3Fixture.start);
    addTearDown(fixture!.close);
    Env.overrideApiBaseUrl(fixture.backend.baseUrl);
    var outage = true;
    final provider = createProductionConversationProvider(
      isSignedIn: () => true,
      send: (request) async {
        if (outage && request.method == 'GET' && Uri.parse(request.url).path == '/v1/conversations') {
          fixture.backend.failNext('GET', '/v1/conversations', status: 503);
        }
        return fixture.send(request);
      },
    );
    addTearDown(provider.dispose);
    expect(provider.usesTypedConversationApi, isTrue);
    final screen = await tester.runAsync(() => buildTypedConversationScreen(provider));
    await tester.pumpWidget(screen!);
    await tester.runAsync(() async {
      await provider.getInitialConversations();
      await pumpEventQueue();
    });
    await tester.pump();
    final page = find.byType(ConversationsPage);
    expect(page, findsOneWidget);
    expect(identical(tester.element(page).read<ConversationProvider>(), provider), isTrue);
    expect(provider.apiViewState.phase, ApiViewPhase.error);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.conversations.error'))), findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byKey(const ValueKey('omi.conversations.empty')), findsNothing);
    outage = false;
    await tester.runAsync(() async => await provider.forceRefreshConversations());
    await tester.pump();
    expect(provider.apiViewState.phase, ApiViewPhase.empty);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.conversations.error'))), findsNothing);
    expect(find.descendant(of: page, matching: find.byKey(const ValueKey('omi.conversations.empty'))), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });
}
