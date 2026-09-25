import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Records the deferred-delete calls instead of starting the provider's real timer.
class _RecordingMemoriesProvider extends MemoriesProvider {
  final List<String> deleted = [];
  final List<String> committed = [];
  int restored = 0;

  @override
  void deleteMemory(Memory memory) => deleted.add(memory.id);

  @override
  Future<bool> restoreLastDeletedMemory({String? id}) async {
    restored++;
    return true;
  }

  @override
  Future<void> confirmPendingDeletion({String? id}) async => committed.add(id ?? '');
}

Memory _memory({String? supersededBy, KnowledgeLedgerKind? kind}) {
  return Memory(
    id: 'mem-1',
    uid: 'uid',
    content: 'Prefers morning meetings',
    category: MemoryCategory.manual,
    createdAt: DateTime.utc(2026, 9, 1),
    updatedAt: DateTime.utc(2026, 9, 1),
    visibility: MemoryVisibility.private,
    ledgerSchemaVersion: kind == null ? null : 'knowledge_ledger.v1',
    ledgerKind: kind,
    supersededBy: supersededBy,
  );
}

Future<void> _open(WidgetTester tester, MemoriesProvider provider, Memory memory) async {
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: TextButton(
              onPressed: () => showMemoryQuickEditSheet(context, memory, provider),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  test('the provider holds a delete back longer than the Undo toast stays up', () {
    expect(MemoriesProvider.pendingDeletionWindow > OmiFeedbackTiming.undo, isTrue);
  });

  testWidgets('delete from the sheet is immediate, closes it and offers Undo without a close button', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    await _open(tester, provider, _memory());

    await tester.tap(find.byTooltip('Delete Memory'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(AlertDialog), findsNothing, reason: 'a restorable delete never asks first (D5)');
    expect(provider.deleted, ['mem-1']);
    expect(find.byType(MemoryEditSheet), findsNothing);
    expect(find.text('Memory deleted'), findsOneWidget);
    expect(find.text('Undo'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsNothing, reason: 'nothing on an undo toast deletes sooner');

    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(provider.restored, 1);
    expect(provider.committed, isEmpty);
  });

  testWidgets('an Undo toast that times out commits exactly the memory it offered', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    await _open(tester, provider, _memory());

    await tester.tap(find.byTooltip('Delete Memory'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500)); // toast arrives
    await tester.pump(OmiFeedbackTiming.undo); // toast times out
    await tester.pumpAndSettle();

    expect(provider.restored, 0);
    expect(provider.committed, ['mem-1']);
  });

  testWidgets('leaving with unsaved text asks first; Keep Editing keeps the draft', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    await _open(tester, provider, _memory());

    // A clean sheet has explicit Cancel and Save.
    expect(find.text('Cancel'), findsOneWidget);
    expect(find.text('Save'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('memory_edit_field')), 'Prefers afternoon meetings');
    await tester.pump();

    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Discard Changes?'), findsOneWidget);

    await tester.tap(find.text('Keep Editing'));
    await tester.pumpAndSettle();
    expect(find.byType(MemoryEditSheet), findsOneWidget);
    expect(find.text('Prefers afternoon meetings'), findsOneWidget);

    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard'));
    await tester.pumpAndSettle();
    expect(find.byType(MemoryEditSheet), findsNothing);
  });

  testWidgets('a clean sheet closes without asking', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    await _open(tester, provider, _memory());

    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Discard Changes?'), findsNothing);
    expect(find.byType(MemoryEditSheet), findsNothing);
  });

  testWidgets('a superseded ledger memory opens read-only', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    await _open(tester, provider, _memory(supersededBy: 'newer', kind: KnowledgeLedgerKind.fact));

    expect(find.text('Memory'), findsOneWidget);
    expect(find.text('Prefers morning meetings'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Save'), findsNothing);
    expect(find.byTooltip('Delete Memory'), findsNothing);
    expect(find.text("This memory is kept as history and can't be edited."), findsOneWidget);
  });

  testWidgets('long-press on a memory row offers Open, Edit and Delete', (tester) async {
    final provider = _RecordingMemoriesProvider();
    addTearDown(provider.dispose);
    var edits = 0;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: MemoryItem(memory: _memory(), provider: provider, onTap: (_, __, ___) => edits++),
        ),
      ),
    );

    await tester.longPress(find.text('Prefers morning meetings'));
    await tester.pumpAndSettle();
    expect(find.text('Open'), findsOneWidget);
    expect(find.text('Edit'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);

    await tester.tap(find.text('Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(provider.deleted, ['mem-1']);
    expect(find.text('Memory deleted'), findsOneWidget);
    expect(edits, 0);
  });
}
