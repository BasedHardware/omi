import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/providers/memories_provider.dart';

/// Regression coverage for the use_build_context_synchronously fix class:
/// a BuildContext used after an `await` without a mounted check crashes when
/// the widget is disposed while the await is in flight. This exercises
/// MemoryEditSheet._showDeleteConfirmation, which awaits
/// DeleteConfirmation.show(context) and then (before the fix) used `context`
/// unconditionally afterward.
///
/// [MemoriesProvider.deleteMemory] starts a real 4-second deletion Timer with
/// no test hook to cancel it, so this fake overrides it to a no-op — this is
/// the same "subclass and override" pattern used by
/// test/widgets/session_expired_reauthentication_test.dart, not a change to
/// production code.
class _FakeMemoriesProvider extends MemoriesProvider {
  bool deleteCalled = false;

  @override
  void deleteMemory(Memory memory) {
    deleteCalled = true;
  }
}

/// Hosts [MemoryEditSheet] and exposes a way to remove it from the tree
/// (via [_HostState.removeSheet]) without needing to hit-test a widget —
/// important because once the delete-confirmation dialog is open, its modal
/// barrier blocks taps to anything behind it.
class _Host extends StatefulWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final VoidCallback onDelete;

  const _Host({super.key, required this.memory, required this.provider, required this.onDelete});

  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  bool _showSheet = true;

  void removeSheet() => setState(() => _showSheet = false);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _showSheet
          ? MemoryEditSheet(
              memory: widget.memory,
              provider: widget.provider,
              onDelete: (ctx, mem, prov) => widget.onDelete(),
            )
          : const SizedBox.shrink(),
    );
  }
}

void main() {
  testWidgets('confirming delete after the sheet is removed from the tree does not throw', (tester) async {
    final memory = Memory(
      id: 'test-memory-id',
      uid: 'test-uid',
      content: 'Test memory content',
      category: MemoryCategory.manual,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      visibility: MemoryVisibility.private,
    );
    final provider = _FakeMemoriesProvider();
    addTearDown(provider.dispose);

    final hostKey = GlobalKey<_HostState>();
    bool onDeleteCalled = false;

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: _Host(key: hostKey, memory: memory, provider: provider, onDelete: () => onDeleteCalled = true),
      ),
    );
    await tester.pump();

    expect(find.byType(MemoryEditSheet), findsOneWidget);

    // Open the delete-confirmation dialog. This starts the await inside
    // _showDeleteConfirmation; the Future does not resolve until the
    // dialog's own button is tapped below.
    await tester.tap(find.byIcon(Icons.delete_outline));
    await tester.pump();

    expect(find.byType(AlertDialog), findsOneWidget);

    // Remove MemoryEditSheet from the tree while the confirmation dialog
    // is still open — the dialog itself lives in the root Navigator's
    // overlay, independent of the sheet's own subtree, so this disposes
    // the sheet's State without touching the open dialog route. Driven
    // directly through the host's State (not a tap) because the dialog's
    // modal barrier blocks hit-testing anything behind it.
    hostKey.currentState!.removeSheet();
    await tester.pump();

    expect(find.byType(MemoryEditSheet), findsNothing);
    expect(find.byType(AlertDialog), findsOneWidget);

    // Confirm the delete. This resumes _showDeleteConfirmation after the
    // await with the sheet's State already disposed. Before the fix, the
    // unconditional `Navigator.pop(context)` / `widget.onDelete!(...)`
    // calls here would throw ("Looking up a deactivated widget's ancestor
    // is unsafe"); the mounted guard must make this a clean no-op instead.
    await tester.tap(find.text('Delete'));
    await tester.pump();

    expect(provider.deleteCalled, isTrue, reason: 'delete still runs regardless of mount state');
    expect(onDeleteCalled, isFalse, reason: 'onDelete/Navigator.pop must be skipped once unmounted');

    // Reaching here without flutter_test raising an unhandled exception
    // (from the FlutterError.onError hook) is the actual assertion.
  });
}
