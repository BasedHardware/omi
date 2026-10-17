import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/providers/action_items_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Records reorders instead of persisting them; every other owner path stays real and inert.
class _TasksOwner extends ActionItemsProvider {
  _TasksOwner()
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
              ActionItemsResponse(actionItems: _fixture()),
          deleteActionItemRequest: (_) async => true,
        );

  final sortOrders = <Map<String, int>>[];

  @override
  void batchUpdateSortOrders(Map<String, int> updates) => sortOrders.add(updates);

  @override
  void updateItemIndentLevel(String id, int indentLevel) {}
}

List<ActionItemWithMetadata> _fixture() {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day, 12);
  return [
    ActionItemWithMetadata(id: 'plan', description: 'Plan the launch', completed: false, sortOrder: 1000, dueAt: today),
    ActionItemWithMetadata(
        id: 'venue', description: 'Book the venue', completed: false, sortOrder: 2000, indentLevel: 1, dueAt: today),
    ActionItemWithMetadata(id: 'notes', description: 'Send the notes', completed: false, sortOrder: 3000, dueAt: today),
  ];
}

/// The page as home/page.dart's native-shell 'tasks' builder mounts it (without the shell's own tab-bar
/// surface, so the harness checks a single UIKit view).
Future<_TasksOwner> _pumpTasksTab(WidgetTester tester) async {
  await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
  addTearDown(JourneyHermeticBoot.stop);
  final owner = _TasksOwner();
  addTearDown(owner.dispose);
  await tester.pumpWidget(nativeHostApp(const Scaffold(body: ActionItemsPage(selectionBarInFallback: true)),
      providers: [ChangeNotifierProvider<ActionItemsProvider>.value(value: owner)]));
  await owner.ensureLoaded();
  await tester.pump();
  return owner;
}

/// Delivers [id] on the native view's channel, as SwiftUI's command does.
Future<void> _sendFromNative(WidgetTester tester, String id, Object? value) async {
  final viewId = nativeViewId(tester, find.byType(UiKitView))!;
  const codec = StandardMethodCodec();
  ByteData? reply;
  await tester.binding.defaultBinaryMessenger.handlePlatformMessage('com.omi.native_ui/surface/$viewId',
      codec.encodeMethodCall(MethodCall('action', {'id': id, 'value': value})), (data) => reply = data);
  codec.decodeEnvelope(reply!);
  await tester.pump();
}

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('native Tasks selection uses the native bottom bar, not the Flutter action bar', (tester) async {
      final owner = await _pumpTasksTab(tester);
      await checkNativeHost(tester, 'native-tasks-selection-hierarchy-tasks-dark');
      expect(nativeProjectedRow(tester, 'task_venue').indent, 1);

      await nativeProjectedRow(tester, 'tasks_menu').action!('select');
      await tester.pump();
      await _sendFromNative(tester, '_selection', ['task_plan']);
      expect(owner.selectedItems, {'plan', 'venue'}, reason: 'selecting a parent selects its visible subtree');
      await checkNativeHost(tester, 'native-tasks-selection-hierarchy-selection-dark');
      expect(find.byType(TaskSelectionActionBar), findsNothing);
      expect(nativeProjectedRow(tester, 'tasks_delete').enabled, isTrue);

      await nativeProjectedRow(tester, 'tasks_cancel').action!(null);
      await tester.pump();
      expect(owner.isSelectionMode, isFalse);
    });

    testWidgets('native Tasks edit mode sends a permutation to the existing sort owner', (tester) async {
      final owner = await _pumpTasksTab(tester);
      await checkNativeHost(tester, 'native-tasks-selection-hierarchy-list-dark');
      await nativeProjectedRow(tester, 'tasks_menu').action!('reorder');
      await tester.pump();
      await checkNativeHost(tester, 'native-tasks-selection-hierarchy-reorder-dark');
      await _sendFromNative(tester, '_reorder:today', ['task_notes', 'task_plan', 'task_venue']);
      expect(owner.sortOrders.single, {'notes': 1000, 'plan': 2000, 'venue': 3000});
    });

    testWidgets('a refused Tasks snapshot restores the Flutter page with its selection bar', (tester) async {
      IosNativeSurface.debugCorruptSnapshotForTest = true;
      addTearDown(() => IosNativeSurface.debugCorruptSnapshotForTest = false);
      final owner = await _pumpTasksTab(tester);
      for (var frame = 0; frame < 20 && find.byType(UiKitView).evaluate().isNotEmpty; frame++) {
        await tester.pump(const Duration(milliseconds: 200));
      }
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(TaskSelectionActionBar), findsOneWidget);
      owner.startSelection();
      await tester.pump(const Duration(seconds: 1));
      expect(await captureNativeHostScreenshot('native-tasks-selection-hierarchy-fallback-dark'), isNotEmpty);
      expect(find.byType(UiKitView), findsNothing, reason: 'selection keeps the refused route on its fallback');
      expect(find.byType(TaskSelectionActionBar), findsOneWidget);
      owner.endSelection();
      await tester.pump(const Duration(seconds: 1));
      expect(tester.takeException(), isNull);
    });
  });
}
