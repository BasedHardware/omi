import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api/task_suggestions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_suggestions_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../integration_test/support/task_delivery_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    Env.overrideApiBaseUrl('http://127.0.0.1:18965/');
  });

  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('production composition only creates a task after approval and reads its exact identity', () async {
    final fixture = TaskDeliveryFixture();
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    await provider.suggestions!.load();
    expect(provider.actionItems, isEmpty);
    expect(fixture.acceptCalls, 0);
    expect(await provider.suggestions!.accept(provider.suggestions!.items.single), isTrue);
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(provider.suggestions!.items, isEmpty);
    await provider.forceRefreshActionItems();
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(fixture.acceptCalls, 1);
  });

  test('saved receipt survives hydration outage; retry never accepts a second time', () async {
    final fixture = TaskDeliveryFixture()..failHydration = true;
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    final state = provider.suggestions!;
    await state.load();
    expect(await state.accept(state.items.single), isTrue);
    expect(state.saved(state.items.single.candidateId), isTrue);
    expect(provider.actionItems, isEmpty);
    fixture.failHydration = false;
    await state.load();
    expect(state.items, isEmpty);
    expect(provider.actionItems.single.id, 'synthetic-task');
    expect(fixture.acceptCalls, 1);
  });

  test('an approved incomplete task is revealed from the Completed view', () async {
    final fixture = TaskDeliveryFixture();
    final provider = createProductionActionItemsProvider(send: fixture.send);
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    provider.toggleShowCompletedView();
    expect(provider.showCompletedView, isTrue);
    await provider.suggestions!.load();
    await provider.suggestions!.accept(provider.suggestions!.items.single);
    expect(provider.showCompletedView, isFalse);
  });

  for (final pagination in [false, true]) {
    for (final manualSelection in [false, true]) {
      test('incoming tasks exit automatic Completed only (pagination: $pagination, manual: $manualSelection)',
          () async {
        final fixture = TaskDeliveryFixture();
        var incoming = false;
        final provider = ActionItemsProvider(
            actionItemsApi: ActionItemsApi(
          baseUrl: 'http://fixture.invalid/',
          send: (request) async {
            final nextPage = Uri.parse(request.url).queryParameters['offset'] != '0';
            return fixture.response({
              'action_items': [
                if (!nextPage) {'id': 'done', 'description': 'Completed task', 'completed': true},
                if (incoming) {'id': 'open', 'description': 'New phone task', 'completed': false},
              ],
              'has_more': pagination && !incoming
            });
          },
        ));
        addTearDown(provider.dispose);
        await provider.ensureLoaded();
        expect(provider.showCompletedView, isTrue);
        if (manualSelection) {
          provider.toggleShowCompletedView();
          provider.toggleShowCompletedView();
        }
        incoming = true;
        if (pagination) {
          await provider.loadMoreActionItems();
        } else {
          await provider.fetchActionItems();
        }
        expect(provider.actionItems.map((item) => item.id), ['done', 'open']);
        expect(provider.showCompletedView, manualSelection);
      });
    }
  }

  for (final undo in [true, false]) {
    test('restoring an open task exits automatic Completed (undo: $undo)', () async {
      final fixture = TaskDeliveryFixture();
      final provider = ActionItemsProvider(
        actionItemsApi: ActionItemsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (_) async => fixture.response({
                  'action_items': [
                    {'id': 'done', 'description': 'Done', 'completed': true},
                    {'id': 'open', 'description': 'Open', 'completed': false},
                  ],
                  'has_more': false,
                })),
        deleteActionItemRequest: (_) async => false,
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      provider.stageDeleteActionItem(provider.actionItems.last);
      await provider.fetchActionItems();
      expect(provider.showCompletedView, isTrue);
      if (undo) {
        await provider.undoStagedDelete('open');
      } else {
        expect(await provider.commitStagedDelete('open'), isFalse);
      }
      expect(provider.showCompletedView, isFalse);
      expect(provider.actionItems.map((item) => item.id), ['done', 'open']);
    });
  }

  test('manual create still lands if a refresh removes its optimistic placeholder', () async {
    final created = Completer<ActionItemWithMetadata?>();
    final provider = ActionItemsProvider(
      getActionItems: (
              {limit = 50,
              offset = 0,
              completed,
              conversationId,
              startDate,
              endDate,
              dueStartDate,
              dueEndDate}) async =>
          const ActionItemsResponse(actionItems: []),
      createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) => created.future,
    );
    addTearDown(provider.dispose);
    await provider.ensureLoaded();
    final saving = provider.createActionItem(description: 'Write the notes');
    await provider.fetchActionItems();
    expect(provider.actionItems, isEmpty);
    created
        .complete(const ActionItemWithMetadata(id: 'created-task', description: 'Write the notes', completed: false));
    expect(await saving, isNotNull);
    expect(provider.actionItems.single.id, 'created-task');
  });

  for (final actor in ['receipt', 'undo', 'optimistic']) {
    test('an older accepted task cannot skip a server row during pagination ($actor)', () async {
      final fixture = TaskDeliveryFixture();
      final created = Completer<ActionItemWithMetadata?>();
      Future<ActionItemWithMetadata?>? saving;
      final rows = List.generate(
          100,
          (index) => {
                'id': index == 80 ? 'synthetic-task' : 'task-$index',
                'description': 'Task $index',
                'completed': false,
              });
      final offsets = <int>[];
      final provider = ActionItemsProvider(
        createActionItemRequest: ({required description, dueAt, conversationId, completed = false}) => created.future,
        actionItemsApi: ActionItemsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (request) async {
              final uri = Uri.parse(request.url);
              if (uri.path != '/v1/action-items') return fixture.send(request);
              final offset = int.parse(uri.queryParameters['offset'] ?? '0');
              offsets.add(offset);
              return fixture.response({'action_items': rows.skip(offset).take(50).toList(), 'has_more': offset == 0});
            }),
        taskSuggestionsApi: TaskSuggestionsApi(baseUrl: 'http://fixture.invalid/', send: fixture.send),
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      await provider.suggestions!.load();
      await provider.suggestions!.accept(provider.suggestions!.items.single);
      expect(provider.actionItems.length, 51);
      if (actor == 'undo') {
        provider.stageDeleteActionItem(provider.actionItems.first);
        await provider.fetchActionItems();
        await provider.undoStagedDelete('synthetic-task');
      } else if (actor == 'optimistic') {
        saving = provider.createActionItem(description: 'New task');
        expect(provider.actionItems.length, 52);
      }
      await provider.loadMoreActionItems();
      expect(offsets, [0, if (actor == 'undo') 0, 50]);
      expect(provider.actionItems.where((item) => !item.id.startsWith('temp_')).map((item) => item.id),
          unorderedEquals(rows.map((row) => row['id'])));
      if (saving != null) {
        created.complete(const ActionItemWithMetadata(id: 'created-task', description: 'New task', completed: false));
        await saving;
        expect(provider.actionItems.map((item) => item.id).toSet().length, 101);
        expect(provider.actionItems.length, 101);
      }
    });
  }

  for (final lane in ['list', 'pagination', 'home']) {
    test('older $lane response cannot erase an accepted task', () async {
      final fixture = TaskDeliveryFixture();
      final oldRead = Completer<http.Response>();
      var delay = false;
      final provider = ActionItemsProvider(
        actionItemsApi: ActionItemsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (request) {
              if (Uri.parse(request.url).path == '/v1/action-items') {
                if (delay) return oldRead.future;
                return Future.value(fixture.response({'action_items': [], 'has_more': true}));
              }
              return fixture.send(request);
            }),
        taskSuggestionsApi: TaskSuggestionsApi(baseUrl: 'http://fixture.invalid/', send: fixture.send),
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      await provider.suggestions!.load();
      delay = true;
      final read = switch (lane) {
        'pagination' => provider.loadMoreActionItems(),
        'home' => provider.ensureHomeTodayTasksLoaded(),
        _ => provider.fetchActionItems(),
      };
      expect(await provider.suggestions!.accept(provider.suggestions!.items.single), isTrue);
      oldRead.complete(fixture.response({'action_items': [], 'has_more': false}));
      await read;
      expect(provider.actionItems.single.id, 'synthetic-task');
    });
  }

  test('late suggestion list cannot resurrect an accepted or dismissed suggestion', () async {
    for (final accept in [true, false]) {
      final fixture = TaskDeliveryFixture();
      final delayed = Completer<http.Response>();
      var delay = false;
      final state = TaskSuggestionsController(
        api: TaskSuggestionsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (request) {
              if (delay && Uri.parse(request.url).path == '/v1/candidates') return delayed.future;
              return fixture.send(request);
            }),
        onTaskSaved: (_) async => true,
      );
      addTearDown(state.dispose);
      await state.load();
      final item = state.items.single;
      delay = true;
      final loading = state.load();
      final staleBody = fixture.response({
        'candidates': [fixture.candidate]
      });
      expect(await (accept ? state.accept(item) : state.dismiss(item)), isTrue);
      delayed.complete(staleBody);
      await loading;
      expect(state.items, isEmpty);
    }
  });

  test('account reset during acceptance cannot hydrate the next account', () async {
    final fixture = TaskDeliveryFixture();
    final receipt = Completer<http.Response>();
    var hydrations = 0;
    final state = TaskSuggestionsController(
      api: TaskSuggestionsApi(
          baseUrl: 'http://fixture.invalid/',
          send: (request) {
            if (request.url.endsWith('/accept')) return receipt.future;
            return fixture.send(request);
          }),
      onTaskSaved: (_) async {
        hydrations++;
        return true;
      },
    );
    addTearDown(state.dispose);
    await state.load();
    final accepted = state.accept(state.items.single);
    state.reset();
    receipt.complete(await fixture.send(const ApiRequest(
      url: 'http://fixture.invalid/v1/candidates/synthetic-candidate/accept',
      method: 'POST',
      headers: {'X-Account-Generation': '7'},
    )));
    expect(await accepted, isFalse);
    expect(hydrations, 0);
    expect(state.items, isEmpty);
  });

  test('summary recovery uses stored coordinates, stable retry key and the durable acceptance path', () async {
    final fixture = TaskDeliveryFixture();
    var fail = true;
    final state = TaskSuggestionsController(
      api: TaskSuggestionsApi(
          baseUrl: 'http://fixture.invalid/',
          send: (request) async {
            if (request.url.endsWith('/from-conversation') && fail) {
              fixture.requests.add(request);
              fail = false;
              return fixture.response({}, 503);
            }
            return fixture.send(request);
          }),
      onTaskSaved: (_) async => true,
    );
    addTearDown(state.dispose);
    expect(await state.addSummaryTask('synthetic-conversation', 2, TaskDeliveryFixture.description), isFalse);
    expect(await state.addSummaryTask('synthetic-conversation', 2, TaskDeliveryFixture.description), isTrue);
    final prepares = fixture.requests.where((request) => request.url.endsWith('/from-conversation')).toList();
    expect(prepares.map((request) => request.headers['Idempotency-Key']).toSet().length, 1);
    expect(jsonDecode(prepares.last.body), {
      'conversation_id': 'synthetic-conversation',
      'action_item_index': 2,
      'expected_description': TaskDeliveryFixture.description,
    });
    expect(fixture.requests.where((r) => r.method == 'POST' && r.url.endsWith('/action-items')), isEmpty);
    expect(await state.addSummaryTask('synthetic-conversation', 2, TaskDeliveryFixture.description), isTrue);
    expect(fixture.acceptCalls, 1);
  });

  for (final terminal in ['rejected', 'expired', 'lapsed']) {
    test('summary retry replaces a $terminal alias after an ambiguous acceptance failure', () async {
      final fixture = TaskDeliveryFixture();
      var prepareCalls = 0;
      var accepts = 0;
      final keys = <String>[];
      final state = TaskSuggestionsController(
        api: TaskSuggestionsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (request) async {
              if (request.url.endsWith('/from-conversation')) {
                prepareCalls++;
                keys.add(request.headers['Idempotency-Key']!);
                if (prepareCalls == 2) {
                  return fixture.response({
                    ...fixture.candidate,
                    'status': terminal == 'lapsed' ? 'pending' : terminal,
                    if (terminal == 'lapsed') 'expires_at': '2000-01-01T00:00:00Z',
                  });
                }
              }
              if (request.url.endsWith('/accept') && ++accepts == 1) return fixture.response({}, 503);
              return fixture.send(request);
            }),
        onTaskSaved: (_) async => true,
      );
      addTearDown(state.dispose);
      expect(await state.addSummaryTask('synthetic-conversation', 0, TaskDeliveryFixture.description), isFalse);
      expect(await state.addSummaryTask('synthetic-conversation', 0, TaskDeliveryFixture.description), isTrue);
      expect(prepareCalls, 3);
      expect(keys[0], keys[1]);
      expect(keys[2], isNot(keys[1]));
      expect(accepts, 2);
      expect(fixture.acceptCalls, 1);
    });
  }

  for (final terminal in [false, true]) {
    test('an acceptance conflict retires only a confirmed terminal retry key ($terminal)', () async {
      final fixture = TaskDeliveryFixture();
      final keys = <String>[];
      var conflict = true;
      final state = TaskSuggestionsController(
        api: TaskSuggestionsApi(
            baseUrl: 'http://fixture.invalid/',
            send: (request) async {
              if (request.url.endsWith('/from-conversation')) keys.add(request.headers['Idempotency-Key']!);
              if (request.url.endsWith('/accept') && conflict) {
                conflict = false;
                return fixture.response({}, 409);
              }
              if (request.method == 'GET' && request.url.endsWith('/synthetic-candidate')) {
                return terminal
                    ? fixture.response({...fixture.candidate, 'status': 'rejected'})
                    : fixture.response({}, 503);
              }
              return fixture.send(request);
            }),
        onTaskSaved: (_) async => true,
      );
      addTearDown(state.dispose);
      expect(await state.addSummaryTask('synthetic-conversation', 0, TaskDeliveryFixture.description), isFalse);
      expect(await state.addSummaryTask('synthetic-conversation', 0, TaskDeliveryFixture.description), isTrue);
      expect(keys.length, 2);
      expect(keys[0] == keys[1], !terminal);
      expect(fixture.acceptCalls, 1);
    });
  }
}
