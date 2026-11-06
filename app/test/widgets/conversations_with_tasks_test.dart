// Production task-filter widgets: stale reads, retry, lifecycle and Android semantics.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/conversation_tasks.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/conversations_with_tasks_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversation_task_presence_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

class _Gateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'widget-owner');
  @override
  AuthUserSnapshot? get currentUser => user;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async => user = null;
}

ServerConversation _row(String id, {bool locked = false}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2020),
      status: ConversationStatus.completed,
      structured: Structured('Conversation $id', ''),
      isLocked: locked,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pump(WidgetTester tester, TaskConversationFetcher fetch, {AuthService? auth, Widget? child}) async {
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversations.dispose);
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: conversations,
        child: MaterialApp(
          theme: ThemeData.dark().copyWith(platform: TargetPlatform.android),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: child ??
              ConversationsWithTasksPage(fetch: fetch, auth: auth ?? AuthService.forTesting(tokenGateway: _Gateway())),
        )));
    await tester.pump();
  }

  for (final repeatedCursor in [false, true]) {
    testWidgets('empty bounded page offers continuation; repeated cursor: $repeatedCursor', (tester) async {
      final cursors = <String?>[];
      Future<ApiResult<TaskConversationPage>> fetch(
          {required String query,
          bool includeDiscarded = false,
          String? folderId,
          bool? starred,
          DateTime? startDate,
          DateTime? endDate,
          String? cursor,
          bool Function()? canSend}) async {
        cursors.add(cursor);
        if (cursors.length == 1) {
          return const ApiSuccess(TaskConversationPage(items: [], nextCursor: 'older', partial: true));
        }
        if (cursors.length == 2) {
          return repeatedCursor
              ? const ApiSuccess(TaskConversationPage(items: [], nextCursor: 'older', partial: true))
              : const ApiFailure(ApiProblem(ApiProblemKind.server));
        }
        return ApiSuccess(TaskConversationPage(items: [_row('older')]));
      }

      await pump(tester, fetch);
      expect(find.text('No results found'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('tasks_filter_more')));
      await tester.pump();
      expect(find.byKey(const ValueKey('tasks_filter_retry')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('tasks_filter_retry')));
      await tester.pump();
      expect(cursors, [null, 'older', repeatedCursor ? null : 'older']);
      expect(find.text('Conversation older'), findsOneWidget);
      expect(find.byKey(const ValueKey('conversation_has_tasks')), findsOneWidget);
    });
  }

  testWidgets('query plus starred is server-side and superseded responses cannot repaint', (tester) async {
    SharedPreferencesUtil().showDiscardedMemories = true;
    final pending = <Completer<ApiResult<TaskConversationPage>>>[];
    final requests = <(String, bool?, bool)>[];
    Future<ApiResult<TaskConversationPage>> fetch(
        {required String query,
        bool includeDiscarded = false,
        String? folderId,
        bool? starred,
        DateTime? startDate,
        DateTime? endDate,
        String? cursor,
        bool Function()? canSend}) {
      requests.add((query, starred, includeDiscarded));
      final result = Completer<ApiResult<TaskConversationPage>>();
      pending.add(result);
      return result.future;
    }

    await pump(tester, fetch);
    await tester.enterText(find.byType(TextField), 'invoice');
    await tester.tap(find.byKey(const ValueKey('tasks_filter_starred')));
    await tester.pump(const Duration(milliseconds: 251));
    expect(requests.last, ('invoice', true, true));
    pending.last.complete(ApiSuccess(TaskConversationPage(items: [_row('current')])));
    await tester.pump();
    pending.first.complete(ApiSuccess(TaskConversationPage(items: [_row('stale')])));
    await tester.pump();
    expect(find.text('Conversation current'), findsOneWidget);
    expect(find.text('Conversation stale'), findsNothing);
  });

  testWidgets('task change refreshes results and account switch clears them before old response', (tester) async {
    final gateway = _Gateway();
    final auth = AuthService.forTesting(tokenGateway: gateway);
    final presence = ConversationTaskPresenceProvider(auth: auth);
    addTearDown(presence.dispose);
    final pending = <Completer<ApiResult<TaskConversationPage>>>[];
    Future<ApiResult<TaskConversationPage>> fetch(
        {required String query,
        bool includeDiscarded = false,
        String? folderId,
        bool? starred,
        DateTime? startDate,
        DateTime? endDate,
        String? cursor,
        bool Function()? canSend}) {
      final result = Completer<ApiResult<TaskConversationPage>>();
      pending.add(result);
      return result.future;
    }

    await pump(tester, fetch,
        child:
            ChangeNotifierProvider.value(value: presence, child: ConversationsWithTasksPage(fetch: fetch, auth: auth)));
    pending.first.complete(ApiSuccess(TaskConversationPage(items: [_row('a')])));
    await tester.pump();
    expect(find.text('Conversation a'), findsOneWidget);
    presence.invalidate();
    await tester.pump(const Duration(milliseconds: 151));
    await tester.pump(const Duration(milliseconds: 251));
    expect(pending.length, 2);
    gateway.user = const AuthUserSnapshot(uid: 'replacement');
    auth.handleAuthUserChanged('replacement');
    await tester.pump();
    expect(find.text('Conversation a'), findsNothing);
    pending.last.complete(ApiSuccess(TaskConversationPage(items: [_row('a')])));
    await tester.pump();
    expect(find.text('Conversation a'), findsNothing);
  });

  testWidgets('badge is accessible at large text and suppressed on locked rows', (tester) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final semantics = tester.ensureSemantics();
    Future<ApiResult<TaskConversationPage>> unused(
            {required String query,
            bool includeDiscarded = false,
            String? folderId,
            bool? starred,
            DateTime? startDate,
            DateTime? endDate,
            String? cursor,
            bool Function()? canSend}) async =>
        const ApiSuccess(TaskConversationPage(items: []));
    await pump(tester, unused,
        child: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(2)),
            child: Scaffold(
                body: ListView(children: [
              ConversationListItem(
                  conversation: _row('a'), date: DateTime.utc(2020), conversationIdx: 0, hasLinkedTasks: true),
              ConversationListItem(
                  conversation: _row('locked', locked: true),
                  date: DateTime.utc(2020),
                  conversationIdx: 1,
                  hasLinkedTasks: true),
            ]))));
    expect(find.bySemanticsLabel(RegExp('Has linked tasks')), findsOneWidget);
    expect(find.byKey(const ValueKey('conversation_has_tasks')), findsOneWidget);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets('access refusal clears cached rows and retry restarts the current filter', (tester) async {
    var calls = 0;
    Future<ApiResult<TaskConversationPage>> fetch(
        {required String query,
        bool includeDiscarded = false,
        String? folderId,
        bool? starred,
        DateTime? startDate,
        DateTime? endDate,
        String? cursor,
        bool Function()? canSend}) async {
      if (++calls == 2) return const ApiFailure(ApiProblem(ApiProblemKind.forbidden, statusCode: 403));
      return ApiSuccess(TaskConversationPage(items: [_row(calls == 1 ? 'old' : 'fresh')]));
    }

    await pump(tester, fetch);
    expect(find.text('Conversation old'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('tasks_filter_refresh')));
    await tester.pump();
    expect(find.text('Conversation old'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('tasks_filter_retry')));
    await tester.pump();
    expect(find.text('Conversation fresh'), findsOneWidget);
  });

  testWidgets('owner replacement followed by a failed request cannot retain old rows', (tester) async {
    final gateway = _Gateway();
    final auth = AuthService.forTesting(tokenGateway: gateway);
    final pending = Completer<ApiResult<TaskConversationPage>>();
    var calls = 0;
    Future<ApiResult<TaskConversationPage>> fetch(
            {required String query,
            bool includeDiscarded = false,
            String? folderId,
            bool? starred,
            DateTime? startDate,
            DateTime? endDate,
            String? cursor,
            bool Function()? canSend}) =>
        ++calls == 1 ? Future.value(ApiSuccess(TaskConversationPage(items: [_row('old')]))) : pending.future;
    await pump(tester, fetch, auth: auth);
    await tester.tap(find.byKey(const ValueKey('tasks_filter_refresh')));
    await tester.pump();
    gateway.user = const AuthUserSnapshot(uid: 'replacement');
    // Exercise the error boundary even before the auth-state event is delivered.
    pending.completeError(TimeoutException('synthetic read timeout'));
    await tester.pump();
    expect(find.text('Conversation old'), findsNothing);
  });

  testWidgets('Home rows react to their selected canonical badge and clear it on refresh', (tester) async {
    var linked = true;
    final presence = ConversationTaskPresenceProvider(
        auth: AuthService.forTesting(tokenGateway: _Gateway()),
        fetch: (ids, current) async => ApiSuccess({for (final id in ids) id: id == 'a' && linked}));
    addTearDown(presence.dispose);
    Future<ApiResult<TaskConversationPage>> unused(
            {required String query,
            bool includeDiscarded = false,
            String? folderId,
            bool? starred,
            DateTime? startDate,
            DateTime? endDate,
            String? cursor,
            bool Function()? canSend}) async =>
        const ApiSuccess(TaskConversationPage(items: []));
    await pump(tester, unused,
        child: ChangeNotifierProvider.value(
            value: presence,
            child: Scaffold(
                body: ListView(children: [
              ConversationListItem(conversation: _row('a'), date: DateTime.utc(2020), conversationIdx: 0),
              ConversationListItem(conversation: _row('b'), date: DateTime.utc(2020), conversationIdx: 1),
            ]))));
    await tester.pump(const Duration(milliseconds: 151));
    expect(find.byKey(const ValueKey('conversation_has_tasks')), findsOneWidget);
    linked = false;
    presence.invalidate();
    await tester.pump(const Duration(milliseconds: 151));
    expect(find.byKey(const ValueKey('conversation_has_tasks')), findsNothing);
  });
}
