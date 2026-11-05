// Native simulator + loopback FastAPI/Firestore-emulator acceptance. No account,
// recordings or production service is used. See backend/docs/conversation-task-filter.md.
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversation_tasks.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/conversations_with_tasks_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversation_task_presence_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';

class _Owner implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'task-filter-native-qa');
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {}
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  Future<void> capture(String name) async {
    final image = await binding.takeScreenshot(name);
    final response = await http.post(Uri.parse('http://127.0.0.1:18966/fixture/screenshot/$name'),
        headers: {'content-type': 'image/png'}, body: image);
    expect(response.statusCode, 200);
  }

  testWidgets('Home badge, global filter, failure/retry, lifecycle and back-position', (tester) async {
    const base = 'http://127.0.0.1:18966/';
    Env.overrideApiBaseUrl(base);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    final client = http.Client();
    addTearDown(client.close);
    Future<http.Response> send(ApiRequest r) =>
        client.post(Uri.parse(r.url), headers: {'content-type': 'application/json'}, body: r.body);
    final auth = AuthService.forTesting(tokenGateway: _Owner());
    final presence = ConversationTaskPresenceProvider(
        auth: auth, fetch: (ids, current) => getConversationTaskPresence(ids, send: send, canSend: current));
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    final scroll = ScrollController();
    addTearDown(scroll.dispose);
    addTearDown(presence.dispose);
    addTearDown(conversations.dispose);
    await client.post(Uri.parse('${base}fixture/reset'));
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: conversations),
          ChangeNotifierProvider.value(value: presence),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
              builder: (context) => Scaffold(
                  appBar: AppBar(title: const Text('Home'), actions: [
                    IconButton(
                        key: const ValueKey('qa_has_tasks'),
                        icon: const Icon(Icons.search),
                        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                            builder: (_) => ConversationsWithTasksPage(
                                auth: auth,
                                fetch: (
                                        {required query,
                                        includeDiscarded = false,
                                        folderId,
                                        starred,
                                        startDate,
                                        endDate,
                                        cursor,
                                        canSend}) =>
                                    getConversationsWithTasks(
                                        query: query,
                                        includeDiscarded: includeDiscarded,
                                        folderId: folderId,
                                        starred: starred,
                                        startDate: startDate,
                                        endDate: endDate,
                                        cursor: cursor,
                                        canSend: canSend,
                                        send: send))))),
                  ]),
                  body: ListView.builder(
                      controller: scroll,
                      itemCount: 30,
                      itemBuilder: (_, index) => ConversationListItem(
                            key: ValueKey('qa_home_$index'),
                            conversation: ServerConversation(
                                id: 'c${index.toString().padLeft(3, '0')}',
                                createdAt: DateTime.utc(2026, 1, 1),
                                status: ConversationStatus.completed,
                                structured: Structured('Home notes $index', '')),
                            date: DateTime.utc(2026),
                            conversationIdx: index,
                          )))),
        )));
    await tester.pumpAndSettle();
    // This badge has no loading animation. Frame settlement alone does not
    // mean its real HTTP request has completed on a busy simulator host.
    final badge = find.byKey(const ValueKey('conversation_has_tasks'));
    for (var attempt = 0; attempt < 200 && badge.evaluate().isEmpty; attempt++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('conversation_has_tasks')), findsOneWidget);
    await capture('home-task-badge');
    await tester.drag(find.byType(ListView).first, const Offset(0, -250));
    await tester.pumpAndSettle();
    final originalPosition = scroll.offset;
    await tester.tap(find.byKey(const ValueKey('qa_has_tasks')));
    await tester.pumpAndSettle();
    expect(find.text('Notes 0'), findsOneWidget);
    expect(find.text('Notes 54'), findsOneWidget);
    expect(find.text('Notes 55'), findsOneWidget);
    await tester.ensureVisible(find.text('Notes 104'));
    expect(find.text('Notes 104'), findsOneWidget, reason: 'the match is outside Home loaded rows');
    await capture('conversations-with-tasks');
    await tester.tap(find.byKey(const ValueKey('tasks_filter_starred')));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(find.text('Notes 55'), findsNothing);
    expect(find.text('Notes 54'), findsOneWidget);
    await client.post(Uri.parse('${base}fixture/failure'),
        body: jsonEncode({'fail': true}), headers: {'content-type': 'application/json'});
    await tester.tap(find.byKey(const ValueKey('tasks_filter_refresh')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('tasks_filter_retry')));
    expect(find.byKey(const ValueKey('tasks_filter_retry')), findsOneWidget);
    await client.post(Uri.parse('${base}fixture/failure'),
        body: '{"fail":false}', headers: {'content-type': 'application/json'});
    await tester.tap(find.byKey(const ValueKey('tasks_filter_retry')));
    await tester.pumpAndSettle();
    expect(find.text('Notes 54'), findsOneWidget);
    await client.post(Uri.parse('${base}fixture/failure'),
        body: '{"fail":true,"status":403}', headers: {'content-type': 'application/json'});
    await tester.tap(find.byKey(const ValueKey('tasks_filter_refresh')));
    await tester.pumpAndSettle();
    expect(find.text('Notes 54'), findsNothing, reason: 'access refusal must hide cached protected rows');
    await client.post(Uri.parse('${base}fixture/failure'),
        body: '{"fail":false}', headers: {'content-type': 'application/json'});
    await tester.tap(find.byKey(const ValueKey('tasks_filter_retry')));
    await tester.pumpAndSettle();
    expect(find.text('Notes 54'), findsOneWidget);
    await client.post(Uri.parse('${base}fixture/delete-first-task'));
    presence.invalidate();
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.text('Notes 0'), findsNothing);
    await tester.tap(find.byTooltip('Back').first);
    await tester.pumpAndSettle();
    expect(scroll.offset, originalPosition);
    expect(tester.takeException(), isNull);
  });
}
