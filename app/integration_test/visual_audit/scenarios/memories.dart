// The Memories page: create, quick edit, search and filter empty states, and swipe-to-delete.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';

import '../harness.dart';

const _preference = 'I prefer morning meetings and keep Fridays free for focused work.';

final memoriesScenarios = <AuditScenario>[
  AuditScenario(
    id: 'memories-manual-memory',
    title: 'Memories: empty, create, save, quick edit, no results, filtered out',
    page: 'lib/pages/memories/page.dart (MemoriesPage)',
    state: 'Fixture-backed MemoriesProvider on an account with no memories; one manual memory is saved during the run',
    run: (a) async {
      final tester = a.tester;
      await a.pump(const MemoriesPage(), providers: [ChangeNotifierProvider(create: (_) => MemoriesProvider())]);
      await a.shot('Open Memories with an empty account', step: 'empty');
      await a.tap(find.byType(FloatingActionButton));
      await a.shot('Tap the add floating action button', step: 'create');
      expect(tester.widget<OmiButton>(find.byKey(const ValueKey('memory_save_button'))).onPressed, isNull);
      await a.tap(find.byKey(const ValueKey('memory_save_button')));
      await a.shot('Tap Save Memory with no content', step: 'empty-save');
      await a.enterText(find.byKey(const ValueKey('memory_content_field')), _preference);
      await a.shot('Enter a preference', step: 'draft');
      await a.tap(find.byKey(const ValueKey('memory_save_button')));
      await a.shot('Save the preference through the fixture backend', step: 'saved');
      await a.tap(find.text(_preference));
      await a.shot('Tap the saved card to open quick edit', step: 'edit');
      globalNavigatorKey.currentState!.pop();
      await a.settle();
      await a.enterText(find.byType(TextField).first, 'weekend');
      await a.shot('Search for a term absent from the saved memory', step: 'no-results');
      expect(find.text('🔍 No memories found'), findsOneWidget);
      await a.tap(find.byKey(const Key('memories_empty_action')));
      expect(find.text(_preference), findsOneWidget);
      final memories = tester.element(find.byType(MemoriesPage)).read<MemoriesProvider>();
      memories.clearCategoryFilter();
      memories.toggleCategoryFilter(MemoryCategory.system);
      await a.settle();
      await a.shot('Filter out the saved manual memory', step: 'filter-empty');
      await a.tap(find.byKey(const Key('memories_empty_action')));
      expect(find.text(_preference), findsOneWidget);
    },
  ),
  AuditScenario(
    id: 'memories-swipe-delete',
    title: 'Memories list, swipe to delete with Undo',
    page: 'lib/pages/memories/page.dart (MemoriesPage)',
    state: 'Fixture-backed MemoriesProvider holding one saved private memory',
    run: (a) async {
      final memories = MemoriesProvider();
      await a.tester.runAsync(
          () => memories.createMemory('Prefers morning meetings and keeps Fridays free.', MemoryVisibility.private));
      await a.pump(const MemoriesPage(), providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)]);
      await a.shot('Memories list with one saved memory', step: 'list');
      await a.tester.drag(find.byType(Dismissible).first, const Offset(-500, 0));
      await a.settle();
      expect(find.text('Undo'), findsOneWidget);
      await a.shot('Swipe the memory row to delete; the Undo toast shows', step: 'undo');
      // Undo before the toast expires, so no delete request is left in flight.
      await a.tap(find.text('Undo'));
      expect(find.text('Prefers morning meetings and keeps Fridays free.'), findsOneWidget);
    },
  ),
];
