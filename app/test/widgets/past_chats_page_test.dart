import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/past_chats_page.dart';
import 'package:omi/providers/message_provider.dart';

class HistoryApi extends ChatSessionsApi {
  bool fail = false;
  int deletes = 0;
  int calls = 0;
  List<ChatSessionSummary> rows = [
    ChatSessionSummary(id: 'past', title: 'Design review', updatedAt: DateTime.utc(2026, 9, 29), messageCount: 2)
  ];
  @override
  Future<ApiResult<List<ChatSessionSummary>>> list({int offset = 0, int limit = 50}) async {
    calls++;
    return fail
        ? const ApiFailure(ApiProblem(ApiProblemKind.server))
        : ApiSuccess(rows.skip(offset).take(limit).toList());
  }

  @override
  Future<ApiResult<void>> delete(String id) async {
    deletes++;
    rows.removeWhere((row) => row.id == id);
    return const ApiSuccess<void>(null);
  }
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  Future<void> pump(WidgetTester tester, MessageProvider provider, {ValueChanged<ChatHistoryChoice?>? selected}) async {
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
              builder: (context) => Scaffold(
                  body: TextButton(
                      child: const Text('Open'),
                      onPressed: () async {
                        final choice = await Navigator.of(context)
                            .push<ChatHistoryChoice>(MaterialPageRoute(builder: (_) => const PastChatsPage()));
                        selected?.call(choice);
                      }))),
        )));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
  }

  testWidgets('history load failure offers Retry, not a false empty history', (tester) async {
    final api = HistoryApi()..fail = true;
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await pump(tester, provider);
    expect(find.text('Design review'), findsNothing);
    expect(find.text('Try Again'), findsOneWidget);
    api.fail = false;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(find.text('Design review'), findsOneWidget);
    expect(api.calls, 2);
  });
  testWidgets('choosing a thread returns its identity without mutating the current draft', (tester) async {
    final provider = MessageProvider(sessionsApi: HistoryApi());
    addTearDown(provider.dispose);
    ChatHistoryChoice? selected;
    await pump(tester, provider, selected: (choice) => selected = choice);
    expect(find.byKey(const Key('past_chats_new')), findsOneWidget);
    expect(find.text('Chat Apps'), findsNothing);
    await tester.tap(find.byKey(const Key('past_chat_past')));
    await tester.pumpAndSettle();
    expect(selected?.session?.id, 'past');
    expect(provider.chatSessionId, isNull);
  });
  testWidgets('delete requires menu and confirmation; Cancel preserves history', (tester) async {
    final api = HistoryApi();
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await pump(tester, provider);
    await tester.longPress(find.byKey(const Key('past_chat_past')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete chat'));
    await tester.pumpAndSettle();
    expect(api.deletes, 0);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(api.deletes, 0);
    expect(find.text('Design review'), findsOneWidget);
  });
  testWidgets('a full history page exposes pagination and keeps previously loaded rows', (tester) async {
    final api = HistoryApi()
      ..rows = List.generate(
          51, (i) => ChatSessionSummary(id: '$i', title: 'Thread $i', updatedAt: DateTime.utc(2026), messageCount: 2));
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await pump(tester, provider);
    await tester.scrollUntilVisible(find.byKey(const Key('past_chats_more')), 500);
    await tester.tap(find.byKey(const Key('past_chats_more')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('past_chat_50')), findsOneWidget);
    expect(api.calls, 2);
  });
}
