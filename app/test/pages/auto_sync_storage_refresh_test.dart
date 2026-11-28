/// Every Manage Storage clear must re-read the device's storage snapshot.
///
/// The Sync page's storage card renders the ring-status snapshot loaded in
/// `initState`. Clearing recordings while the page stayed open deleted the files
/// but left that snapshot untouched, so the card kept reporting the device full
/// (472 MB of 472 MB used, 12 KB free) until the user navigated away and back.
///
/// Every scope goes through `runStorageClear`, so the re-read is asserted for
/// each scope there, including a clear that did not finish.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/storage_clear_flow.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/storage_clear.dart';

class _Sync extends ChangeNotifier implements SyncProvider {
  _Sync(this.calls, {this.failed = false});

  final List<String> calls;
  final bool failed;

  @override
  Future<StorageClearOutcome> clearStorage(
    StorageClearScope scope, {
    String? firmwareVersion,
    void Function(StorageClearProgress progress)? onProgress,
    Duration settleTimeout = const Duration(seconds: 20),
  }) async {
    calls.add('clear ${scope.name}');
    onProgress?.call(const StorageClearProgress(StorageClearPhase.deleting, done: 1, total: 2));
    return StorageClearOutcome(
      targetSeconds: 120,
      targetCount: 2,
      remainingSeconds: failed ? 60 : 0,
      remainingCount: failed ? 1 : 0,
      remainingOnDeviceSeconds: 0,
      failed: failed,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const _amounts = StorageAmounts(
  uploadedSeconds: 60,
  uploadedCount: 1,
  phonePendingSeconds: 60,
  devicePendingSeconds: 0,
  pendingCount: 1,
  allCount: 2,
  allSeconds: 120,
);

Future<void> _run(WidgetTester tester, StorageClearScope scope, _Sync sync, List<String> calls) async {
  late BuildContext page;
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: Scaffold(body: Builder(builder: (context) {
      page = context;
      return const SizedBox.expand();
    })),
  ));
  final done = runStorageClear(
    context: page,
    provider: sync,
    scope: scope,
    amounts: _amounts,
    afterClear: () async => calls.add('refresh'),
  );
  await tester.pumpAndSettle();
  final l = AppLocalizations.of(page);
  final confirm = switch (scope) {
    StorageClearScope.uploaded => l.storageFreeUpSpace,
    StorageClearScope.notUploaded => l.delete,
    StorageClearScope.all => l.storageDeleteEverything,
  };
  await tester.tap(find.text(confirm).last);
  await tester.pumpAndSettle();
  await done;
}

void main() {
  for (final scope in StorageClearScope.values) {
    testWidgets('${scope.name}: the storage snapshot is re-read after the clear', (tester) async {
      final calls = <String>[];
      await _run(tester, scope, _Sync(calls), calls);
      // Order is the whole point: a read taken before the clear returns the
      // pre-clear numbers, which is the stale reading users were left looking at.
      expect(calls, ['clear ${scope.name}', 'refresh']);
      expect(find.text('Deleted 2m'), findsOneWidget);
    });
  }

  testWidgets('a clear that left audio behind still re-reads storage and says what is left', (tester) async {
    final calls = <String>[];
    await _run(tester, StorageClearScope.notUploaded, _Sync(calls, failed: true), calls);
    expect(calls, ['clear notUploaded', 'refresh']);
    expect(find.text("Deleted 1m. 1m couldn't be deleted."), findsOneWidget);
  });

  testWidgets('cancelling the confirm deletes nothing and re-reads nothing', (tester) async {
    final calls = <String>[];
    late BuildContext page;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: Builder(builder: (context) {
        page = context;
        return const SizedBox.expand();
      })),
    ));
    final done = runStorageClear(
      context: page,
      provider: _Sync(calls),
      scope: StorageClearScope.all,
      amounts: _amounts,
      afterClear: () async => calls.add('refresh'),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(AppLocalizations.of(page).cancel));
    await tester.pumpAndSettle();
    await done;
    expect(calls, isEmpty);
  });
}
