import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

/// Every mutation the page asks of its owner; the fake records them instead of reaching a server.
class _Calls {
  final sortOrders = <Map<String, int>>[];
  final indents = <(String, int)>[];
  final dueDates = <(String, DateTime?)>[];
  final completions = <(String, bool)>[];
  final deleted = <String>[];
  var bulkDeletes = 0;
}

class _FakeTasks extends ActionItemsProvider {
  _FakeTasks(List<ActionItemWithMetadata> items, this.calls)
      : super(
          getActionItems: ({
            int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate,
            DateTime? dueStartDate,
            DateTime? dueEndDate,
          }) async =>
              ActionItemsResponse(actionItems: items),
          deleteActionItemRequest: (id) async {
            calls.deleted.add(id);
            return true;
          },
        );

  final _Calls calls;

  @override
  void batchUpdateSortOrders(Map<String, int> updates) => calls.sortOrders.add(updates);

  @override
  void updateItemIndentLevel(String id, int indentLevel) => calls.indents.add((id, indentLevel));

  @override
  Future<bool> updateActionItemDueDate(ActionItemWithMetadata item, DateTime? dueDate) async {
    calls.dueDates.add((item.id, dueDate));
    return true;
  }

  @override
  Future<bool> updateActionItemState(ActionItemWithMetadata item, bool newState) async {
    calls.completions.add((item.id, newState));
    return true;
  }

  @override
  Future<bool> deleteActionItem(ActionItemWithMetadata item) async {
    calls.deleted.add(item.id);
    return true;
  }

  @override
  Future<bool> deleteSelectedItems({BuildContext? context}) async {
    calls.bulkDeletes++;
    endSelection();
    return true;
  }
}

/// A list whose last load ended in [phase] while more pages remained.
class _FailedTasks extends _FakeTasks {
  _FailedTasks(this.phase, _Calls calls) : super([], calls);
  final ApiViewPhase phase;

  @override
  ApiViewState<List<ActionItemWithMetadata>> get apiViewState => ApiViewState(phase: phase);

  @override
  bool get hasMore => true;
}

class _Integrations extends TaskIntegrationProvider {
  _Integrations({this.connected = false});
  final bool connected;

  @override
  bool get hasLoaded => true;

  @override
  bool isAppConnected(TaskIntegrationApp app) => connected && app == TaskIntegrationApp.todoist;
}

final _now = DateTime.now();
final _today = DateTime(_now.year, _now.month, _now.day, 12);

ActionItemWithMetadata _task(String id,
        {int sortOrder = 0,
        int indent = 0,
        DateTime? dueAt,
        bool completed = false,
        bool exported = false,
        DateTime? createdAt}) =>
    ActionItemWithMetadata(
        id: id,
        description: 'Task $id',
        completed: completed,
        sortOrder: sortOrder,
        indentLevel: indent,
        dueAt: dueAt,
        createdAt: createdAt ?? _now,
        exported: exported,
        exportPlatform: exported ? 'todoist' : null);

/// Today holds a hierarchy (parent > child > grandchild, then sibling); the other categories one row each.
List<ActionItemWithMetadata> _fixture() => [
      _task('parent', sortOrder: 1000, dueAt: _today),
      _task('child', sortOrder: 2000, indent: 1, dueAt: _today),
      _task('grandchild', sortOrder: 3000, indent: 2, dueAt: _today),
      _task('sibling', sortOrder: 4000, dueAt: _today),
      _task('loose'),
      _task('late', dueAt: _today.subtract(const Duration(days: 2))),
      _task('shipped', dueAt: _today.add(const Duration(days: 1)), exported: true),
      _task('done', dueAt: _today, completed: true),
    ];

/// Answers each native presentation with [reply] for its snapshot, and records the snapshots.
List<Map> _answerPresentations(Map<String, Object?> Function(Map snapshot) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    return reply(snapshot);
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

Map<String, Object?> _confirm(Map _) => {'action': 'confirm', 'values': <String, Object?>{}};
Map<String, Object?> _cancel(Map _) => {'action': null, 'values': <String, Object?>{}};

/// Chooses the presented action titled [title].
Map<String, Object?> Function(Map) _choose(String title) => (snapshot) => {
      'action': (snapshot['toolbar'] as List).cast<Map>().firstWhere((row) => row['title'] == title)['id'],
      'values': <String, Object?>{},
    };

class _Page {
  _Page(this.tester, this.host, this.provider, this.calls);
  final WidgetTester tester;
  final NativeTestHost host;
  final _FakeTasks provider;
  final _Calls calls;

  IosNativeSurface get surface => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
  NativeSection section(String id) => surface.sections.firstWhere((section) => section.id == id);
  NativeRow row(String id) => [
        ...surface.toolbar,
        ...surface.bottomBar,
        ...surface.sections.expand((section) => section.rows),
      ].firstWhere((row) => row.id == id);
  NativeRow task(String id) => row('task_$id');

  /// Sends [id] from the native view, as Swift's command would, and rethrows a refusal.
  Future<void> send(String id, [Object? value]) async {
    final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
    const StandardMethodCodec().decodeEnvelope(reply!);
    await tester.pump();
    await tester.pump();
  }
}

Future<_Page> _pump(WidgetTester tester,
    {bool connected = false, List<ActionItemWithMetadata>? items, ApiViewPhase? failedPhase}) async {
  final host = NativeTestHost.install();
  final calls = _Calls();
  final provider = failedPhase == null ? _FakeTasks(items ?? _fixture(), calls) : _FailedTasks(failedPhase, calls);
  addTearDown(provider.dispose);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
      ChangeNotifierProvider<ActionItemsProvider>.value(value: provider),
      ChangeNotifierProvider(create: (_) => GoalsProvider()),
      ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => _Integrations(connected: connected)),
    ],
    child: const MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: [Locale('en')],
      home: Scaffold(body: ActionItemsPage(selectionBarInFallback: true)),
    ),
  ));
  await provider.ensureLoaded();
  await NativeTestHost.settle(tester);
  return _Page(tester, host, provider, calls);
}

Matcher get _refused =>
    throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'invalid_native_action'));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  group('selection', () {
    testWidgets('stays native with label rows, a selection and the bottom bar', (tester) async {
      final page = await _pump(tester);
      expect(page.surface.selection, isNull);
      expect(page.surface.bottomBar, isEmpty);

      await page.send('tasks_menu', 'select');
      expect(page.provider.isSelectionMode, isTrue);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'selection no longer falls back');
      expect(find.byType(TaskSelectionActionBar), findsNothing, reason: 'the native bottom bar replaces it');
      expect(page.surface.title, _l10n.selectedCount(0));
      expect(page.surface.toolbar.map((row) => row.id), ['tasks_cancel', 'tasks_select_all', 'tasks_completed']);
      expect(page.task('child').kind, 'label');
      expect(page.task('child').indent, 1);
      expect(page.task('child').symbol, 'circle');
      expect(page.surface.selection!.selectable,
          {'task_parent', 'task_child', 'task_grandchild', 'task_sibling', 'task_loose', 'task_late', 'task_shipped'});
      expect(page.surface.selection!.validFor(page.surface.sections), isTrue);
      expect(page.row('tasks_delete').enabled, isFalse);
      expect(page.row('tasks_export').title, _l10n.exportButton);

      await page.send('_selection', ['task_loose']);
      expect(page.surface.title, _l10n.selectedCount(1));
      expect(page.row('tasks_selected_count').title, _l10n.selectedCount(1));
      expect(page.row('tasks_delete').enabled, isTrue);
      expect(page.row('tasks_export').title, '${_l10n.exportButton} · 1');

      await page.send('tasks_cancel');
      expect(page.provider.isSelectionMode, isFalse);
      expect(page.surface.selection, isNull);
    });

    testWidgets("'_selection' cascades additions and removals to visible descendants", (tester) async {
      final page = await _pump(tester);
      await page.send('task_child', 'select');
      expect(page.provider.selectedItems, {'child'});

      await page.send('_selection', ['task_child', 'task_parent']);
      expect(page.provider.selectedItems, {'parent', 'child', 'grandchild'});
      expect(page.surface.selection!.selected, {'task_parent', 'task_child', 'task_grandchild'});

      await page.send('_selection', ['task_parent', 'task_grandchild']);
      expect(page.provider.selectedItems, {'parent'}, reason: 'deselecting child also deselects grandchild');

      await expectLater(page.send('_selection', ['task_parent', 'task_parent']), _refused);
      expect(page.provider.selectedItems, {'parent'}, reason: 'duplicate ids are refused');
      await expectLater(page.send('_selection', ['task_unknown']), _refused);

      await page.send('_selection', ['task_child', 'task_grandchild']);
      expect(page.provider.selectedItems, {'child', 'grandchild'},
          reason: 'removing parent drops its subtree; the re-added rows stay');
    });

    testWidgets('select all and deselect all switch labels and owners', (tester) async {
      final page = await _pump(tester);
      expect(page.row('tasks_menu').options['selectAll'], _l10n.selectAllTasksMenu);

      await page.send('tasks_menu', 'selectAll');
      expect(page.provider.isSelectionMode, isTrue);
      expect(page.provider.selectedCount, page.provider.actionItems.length);
      expect(page.row('tasks_select_all').title, _l10n.deselectAllTasksMenu);
      expect(page.surface.selection!.selected, page.surface.selection!.selectable,
          reason: 'hidden completed tasks are selected but never projected');

      await page.send('tasks_select_all');
      expect(page.provider.selectedItems, isEmpty);
      expect(page.row('tasks_select_all').title, _l10n.selectAllTasksMenu);

      await page.send('tasks_select_all');
      expect(page.provider.selectedCount, page.provider.actionItems.length);
    });

    testWidgets('bulk delete runs only after the confirmation', (tester) async {
      final page = await _pump(tester);
      var confirm = false;
      final presented = _answerPresentations((snapshot) => confirm ? _confirm(snapshot) : _cancel(snapshot));
      await page.send('task_loose', 'select');

      await page.send('tasks_delete');
      await tester.pump();
      expect(presented.single['title'], _l10n.deleteTasksTitle(1));
      expect(page.calls.bulkDeletes, 0);
      expect(page.provider.isSelectionMode, isTrue);

      confirm = true;
      await page.send('tasks_delete');
      await tester.pump();
      expect(page.calls.bulkDeletes, 1);
      expect(page.provider.isSelectionMode, isFalse);
    });

    testWidgets('export without a connected task app offers Connect', (tester) async {
      final page = await _pump(tester);
      await page.send('task_loose', 'select');
      await page.send('tasks_export');
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text(_l10n.connectTaskAppToExport), findsOneWidget);
      expect(find.text(_l10n.connectAction), findsOneWidget);
      expect(page.provider.isSelectionMode, isTrue);
      await tester.pump(const Duration(seconds: 10));
    });

    testWidgets('leaving the page ends the native selection', (tester) async {
      final page = await _pump(tester);
      await page.send('task_parent', 'select');
      expect(page.provider.isSelectionMode, isTrue);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(page.provider.isSelectionMode, isFalse);
    });

    testWidgets('export to the connected app exits selection', (tester) async {
      final page = await _pump(tester, connected: true);
      await page.send('task_shipped', 'select');
      await page.send('tasks_export');
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text(_l10n.bulkExportAlreadyExported), findsOneWidget, reason: 'exported tasks are skipped');
      expect(page.provider.isSelectionMode, isFalse);
      expect(page.surface.selection, isNull);
      expect(page.surface.bottomBar, isEmpty);
      await tester.pump(const Duration(seconds: 10));
    });
  });

  group('rows', () {
    testWidgets('offer indent and outdent only within the hierarchy bounds', (tester) async {
      final page = await _pump(tester);
      expect(page.task('parent').options.keys, isNot(contains('indent')), reason: 'the first row never indents');
      expect(page.task('parent').options.keys, isNot(contains('outdent')));
      expect(page.task('child').options.keys, isNot(contains('indent')), reason: 'already one below its parent');
      expect(page.task('child').options.keys, contains('outdent'));
      expect(page.task('grandchild').options.keys, isNot(contains('indent')));
      expect(page.task('sibling').options.keys, contains('indent'));
      expect(page.task('sibling').subtitle, isNotEmpty);
      expect(page.task('shipped').subtitle, contains(_l10n.exportedToPlatform('Todoist')));

      await page.send('task_sibling', 'indent');
      await page.send('task_grandchild', 'outdent');
      expect(page.calls.indents, [('sibling', 1), ('grandchild', 1)]);
    });

    testWidgets("'due' moves the task with the drag and drop dates", (tester) async {
      final page = await _pump(tester);
      var choice = _l10n.tomorrow;
      final presented = _answerPresentations((snapshot) => _choose(choice)(snapshot));
      await page.send('task_loose', 'due');
      await tester.pump();
      final titles = (presented.single['toolbar'] as List).cast<Map>().map((row) => row['title']);
      expect(titles, containsAll([_l10n.today, _l10n.tomorrow, _l10n.tasksLater, _l10n.tasksOverdue]));
      expect(titles, isNot(contains(_l10n.tasksNoDeadline)), reason: 'the current category is not offered');
      final day = DateTime(_now.year, _now.month, _now.day);
      final expected = {
        _l10n.today: DateTime(day.year, day.month, day.day, 23, 59),
        _l10n.tomorrow: DateTime(day.year, day.month, day.day + 1, 23, 59),
        _l10n.tasksLater: DateTime(day.year, day.month, day.day + 2, 23, 59),
        _l10n.tasksOverdue: DateTime(day.year, day.month, day.day - 1, 23, 59),
      };
      for (final MapEntry(key: title, value: date) in expected.entries) {
        choice = title;
        await page.send('task_loose', 'due');
        await tester.pump();
        expect(page.calls.dueDates.last, ('loose', date), reason: title);
      }
      expect(page.calls.dueDates.first, ('loose', expected[_l10n.tomorrow]));
      choice = _l10n.tasksNoDeadline;
      await page.send('task_parent', 'due');
      await tester.pump();
      expect(page.calls.dueDates.last, ('parent', null));

      choice = _l10n.tomorrow;
      await page.send('tasks_menu', 'completed');
      await page.send('task_done', 'due');
      await tester.pump();
      final completedTitles = (presented.last['toolbar'] as List).cast<Map>().map((row) => row['title']);
      expect(completedTitles, isNot(contains(_l10n.tasksOverdue)), reason: 'the completed view has no Overdue');
      expect(completedTitles, isNot(contains(_l10n.today)));
    });

    testWidgets('swipes route to complete and to delete with Undo', (tester) async {
      final page = await _pump(tester);
      expect(page.task('child').swipeLeading, ['complete']);
      expect(page.task('child').swipeTrailing, ['delete']);
      expect(page.task('child').options['complete'], _l10n.markComplete);

      await page.send('task_child', 'complete');
      expect(page.calls.completions, [('child', true)]);

      await page.send('task_child', 'delete');
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text(_l10n.actionItemDeleted), findsOneWidget);
      expect(page.provider.isDeleteStaged('child'), isTrue, reason: 'the server delete waits for the Undo window');
      expect(page.provider.actionItems.map((item) => item.id), isNot(contains('child')));
      for (var second = 0; second < 12; second++) {
        await tester.pump(const Duration(seconds: 1));
      }
    });
  });

  group('sections', () {
    testWidgets('count footers, collapse only Overdue and No deadline, and clear completed after confirm',
        (tester) async {
      final page = await _pump(tester);
      expect(page.surface.sections.map((section) => section.id), ['today', 'tomorrow', 'noDeadline', 'overdue']);
      expect(page.section('today').footer, _l10n.tasksCountLabel(4));
      expect({for (final section in page.surface.sections) section.id: section.collapsible},
          {'today': false, 'tomorrow': false, 'noDeadline': true, 'overdue': true});
      expect(page.surface.sections.expand((section) => section.rows).where((row) => row.id.startsWith('tasks_clear')),
          isEmpty);

      await page.send('tasks_menu', 'completed');
      expect(page.surface.sections.map((section) => section.id), ['today']);
      var confirm = false;
      final presented = _answerPresentations((snapshot) => confirm ? _confirm(snapshot) : _cancel(snapshot));
      await page.send('tasks_clear_today');
      await tester.pump();
      expect(presented, hasLength(1));
      expect(page.calls.deleted, isEmpty);

      confirm = true;
      await page.send('tasks_clear_today');
      await tester.pump();
      expect(page.calls.deleted, ['done']);
    });

    testWidgets('an empty list explains how tasks are created', (tester) async {
      final page = await _pump(tester, items: []);
      expect(page.row('tasks_empty').title, _l10n.noTasksYet);
      expect(page.row('tasks_empty').subtitle, _l10n.tasksEmptyStateMessage);
      expect(page.surface.empty, _l10n.noTasksYet);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'the empty projection stays native');
    });

    testWidgets('a failed load shows the Flutter status copy and no Show more', (tester) async {
      for (final phase in [ApiViewPhase.error, ApiViewPhase.locked, ApiViewPhase.authenticationRequired]) {
        final page = await _pump(tester, failedPhase: phase);
        expect(page.surface.failed, isTrue);
        expect(page.surface.errorMessage, _l10n.somethingWentWrong);
        expect(page.surface.sections.map((section) => section.id), isNot(contains('pagination')));
        expect(find.byType(UiKitView), findsOneWidget, reason: 'the failed projection stays native');
      }
    });

    testWidgets('a search without matches says so', (tester) async {
      final page = await _pump(tester);
      await page.send('_search', 'nothing matches this');
      expect(page.surface.sections.map((section) => section.id), ['empty']);
      expect(page.row('tasks_no_results').title, _l10n.noResultsFound);
      expect(page.surface.empty, _l10n.noResultsFound);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'the no-results projection stays native');
    });

    testWidgets('search results are one flat list of open and completed matches', (tester) async {
      final page = await _pump(tester);
      await page.send('_search', 'Task d');
      expect(page.surface.sections.map((section) => section.id), ['search']);
      expect(page.section('search').rows.map((row) => row.id), ['task_done']);
      expect(page.section('search').footer, _l10n.tasksCountLabel(1));
    });
  });

  group('reorder', () {
    testWidgets('an exact permutation stores sort orders and clamps the moved row', (tester) async {
      final page = await _pump(tester);
      expect(page.section('today').reorder, isNull);
      await page.send('tasks_menu', 'reorder');
      expect(page.surface.toolbar.map((row) => row.id), contains('tasks_reorder_done'));
      expect(
          page.surface.sections.where((section) => section.id != 'pagination').every((s) => s.reorder != null), isTrue);

      await page.send('_reorder:today', ['task_grandchild', 'task_parent', 'task_child', 'task_sibling']);
      expect(page.calls.sortOrders, [
        {'grandchild': 1000, 'parent': 2000, 'child': 3000, 'sibling': 4000}
      ]);
      expect(page.calls.indents, [('grandchild', 0)], reason: 'a first row cannot stay indented');

      await page.send('_reorder:today', ['task_parent', 'task_child', 'task_sibling', 'task_grandchild']);
      expect(page.calls.indents.last, ('grandchild', 1), reason: 'one below the sibling it now follows');

      await page.send('tasks_reorder_done');
      expect(page.surface.sections.every((section) => section.reorder == null), isTrue);
    });

    testWidgets('rejects duplicate, missing, extra, foreign and stale permutations', (tester) async {
      final page = await _pump(tester);
      await page.send('tasks_menu', 'reorder');
      const today = ['task_parent', 'task_child', 'task_grandchild', 'task_sibling'];
      await expectLater(
          page.send('_reorder:today', ['task_parent', 'task_parent', 'task_grandchild', 'task_sibling']), _refused);
      await expectLater(page.send('_reorder:today', today.take(3).toList()), _refused);
      await expectLater(page.send('_reorder:today', [...today, 'task_loose']), _refused);
      await expectLater(page.send('_reorder:noDeadline', ['task_parent']), _refused);
      await expectLater(page.send('_reorder:missing', today), _refused);

      // The owner changes before the surface rebuilds: the projection still accepts the old order, the page refuses.
      page.provider.stageDeleteActionItem(page.provider.actionItems.firstWhere((item) => item.id == 'sibling'));
      await expectLater(page.send('_reorder:today', today), _refused, reason: 'a removed row makes it stale');
      await tester.pump();
      await expectLater(page.send('_reorder:today', today), _refused, reason: 'and the new projection refuses it too');
      expect(page.calls.sortOrders, isEmpty);
      expect(page.calls.indents, isEmpty);
    });

    testWidgets('is unavailable while searching or selecting', (tester) async {
      final page = await _pump(tester);
      await page.send('_search', 'Task');
      expect(page.row('tasks_menu').options.keys, isNot(contains('reorder')));

      await page.send('_search', '');
      await page.send('tasks_menu', 'reorder');
      expect(page.section('today').reorder, isNotNull);
      await page.send('_search', 'Task');
      expect(page.surface.sections.every((section) => section.reorder == null), isTrue);
      await page.send('_search', '');
      expect(page.surface.sections.every((section) => section.reorder == null), isTrue,
          reason: 'searching ends edit mode');

      await page.send('task_parent', 'select');
      expect(page.surface.toolbar.map((row) => row.id), isNot(contains('tasks_menu')));
      expect(page.surface.sections.every((section) => section.reorder == null), isTrue);
    });
  });
}
