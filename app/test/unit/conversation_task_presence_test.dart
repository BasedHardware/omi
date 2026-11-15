// Badge-reader batching, lifecycle invalidation and account isolation regressions.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversation_task_presence_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

class TaskFilterGateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'task-owner');
  @override
  AuthUserSnapshot? get currentUser => user;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async => user = null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('production task refresh and conversation notifications invalidate bound badges', (tester) async {
    final tasks = ActionItemsProvider(
        getActionItems: (
                {limit = 100,
                offset = 0,
                completed,
                conversationId,
                startDate,
                endDate,
                dueStartDate,
                dueEndDate}) async =>
            const ActionItemsResponse(actionItems: [], hasMore: false));
    final conversations = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true), isSignedIn: () => true);
    var linked = true;
    final presence = ConversationTaskPresenceProvider(
        auth: AuthService.forTesting(tokenGateway: TaskFilterGateway()),
        fetch: (ids, current) async => ApiSuccess({for (final id in ids) id: linked}));
    presence.bind(conversations, tasks);
    addTearDown(presence.dispose);
    addTearDown(tasks.dispose);
    addTearDown(conversations.dispose);
    await tasks.ensureLoaded();
    presence.request('a');
    await tester.pump(const Duration(milliseconds: 151));
    expect(presence.presence('a'), isTrue);
    final revision = presence.taskRevision;
    tasks.startSelection();
    tasks.endSelection();
    conversations.enterSelectionMode();
    conversations.exitSelectionMode();
    await tester.pump(const Duration(milliseconds: 151));
    expect(presence.taskRevision, revision, reason: 'selection must not trigger metadata network reads');
    linked = false;
    await tasks.forceRefreshActionItems();
    await tester.pump(const Duration(milliseconds: 151));
    expect(presence.presence('a'), isFalse);
    linked = true;
    conversations.clearUserData();
    await tester.pump(const Duration(milliseconds: 151));
    expect(presence.presence('a'), isTrue);
  });

  testWidgets('visible requests batch; canonical mutations replace both true and false', (tester) async {
    final gateway = TaskFilterGateway();
    final auth = AuthService.forTesting(tokenGateway: gateway);
    final batches = <List<String>>[];
    final owners = <bool>[];
    var hasTasks = true;
    final provider = ConversationTaskPresenceProvider(
        auth: auth,
        fetch: (ids, current) async {
          owners.add(current());
          batches.add(ids);
          return ApiSuccess({for (final id in ids) id: hasTasks});
        });
    addTearDown(provider.dispose);
    provider.request('a');
    provider.request('b');
    provider.request('a');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 151));
    expect(batches, [
      ['a', 'b']
    ]);
    expect(owners, [true]);
    expect(provider.presence('a'), isTrue);
    hasTasks = false;
    provider.invalidate();
    expect(provider.presence('a'), isNull, reason: 'a deleted last task cannot retain a stale positive badge');
    await tester.pump(const Duration(milliseconds: 151));
    expect(provider.presence('a'), isFalse);
    hasTasks = true;
    provider.invalidate();
    await tester.pump(const Duration(milliseconds: 151));
    expect(provider.presence('b'), isTrue);
  });

  testWidgets('failure stays unknown, with bounded explicit retry', (tester) async {
    var calls = 0;
    final provider = ConversationTaskPresenceProvider(
      auth: AuthService.forTesting(tokenGateway: TaskFilterGateway()),
      fetch: (ids, current) async => ++calls == 1
          ? const ApiFailure(ApiProblem(ApiProblemKind.server))
          : ApiSuccess({for (final id in ids) id: false}),
    );
    addTearDown(provider.dispose);
    provider.request('a');
    await tester.pump(const Duration(milliseconds: 151));
    expect(provider.presence('a'), isNull);
    await tester.pump(const Duration(seconds: 5));
    expect(calls, 1);
    provider.request('a');
    await tester.pump(const Duration(milliseconds: 151));
    expect(calls, 1, reason: 'rebuilding a visible row cannot spin on a failed read');
    provider.invalidate();
    await tester.pump(const Duration(milliseconds: 151));
    expect(provider.presence('a'), isFalse);
  });

  testWidgets('old response cannot repaint or prevent same-id replacement-owner read', (tester) async {
    final gateway = TaskFilterGateway();
    final auth = AuthService.forTesting(tokenGateway: gateway);
    final old = Completer<ApiResult<Map<String, bool>>>();
    var calls = 0;
    bool Function()? oldCurrent;
    final provider = ConversationTaskPresenceProvider(
        auth: auth,
        fetch: (ids, current) {
          if (++calls == 1) {
            oldCurrent = current;
            return old.future;
          }
          return Future.value(ApiSuccess({for (final id in ids) id: false}));
        });
    addTearDown(provider.dispose);
    provider.request('a');
    await tester.pump(const Duration(milliseconds: 151));
    gateway.user = const AuthUserSnapshot(uid: 'replacement');
    auth.handleAuthUserChanged('replacement');
    provider.request('a');
    expect(oldCurrent!(), isFalse);
    await tester.pump(const Duration(milliseconds: 151));
    expect(calls, 2, reason: 'replacement must not wait for the old network request');
    old.complete(const ApiSuccess({'a': true}));
    await tester.pump();
    expect(provider.presence('a'), isFalse);
  });
}
