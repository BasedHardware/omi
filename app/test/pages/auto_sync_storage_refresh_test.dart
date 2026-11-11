/// Every Manage Storage clear must re-read the device's storage snapshot.
///
/// The Sync page's storage card renders the ring-status snapshot loaded in
/// `initState`. Clearing recordings while the page stayed open deleted the files
/// but left that snapshot untouched, so the card kept reporting the device full
/// (472 MB of 472 MB used, 12 KB free) until the user navigated away and back —
/// which re-ran the page-open read and showed the true 0 B.
///
/// All three actions are asserted individually. The defect was three handlers
/// that each had to remember the re-read, so a test covering only one of them
/// would let the other two regress.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/auto_sync_page.dart';

void main() {
  /// Build the three actions over one shared call log, so each test can assert
  /// what its action did and — just as importantly — what the others did not.
  ({
    List<String> calls,
    ({Future<void> Function() synced, Future<void> Function() pending, Future<void> Function() all}) actions
  }) subject({Future<void> Function()? clearPending}) {
    final calls = <String>[];
    return (
      calls: calls,
      actions: buildStorageClearActions(
        clearSynced: () async => calls.add('clear synced'),
        clearPending: clearPending ?? () async => calls.add('clear pending'),
        clearAll: () async => calls.add('clear all'),
        refreshDeviceStorage: () async => calls.add('refresh'),
      ),
    );
  }

  test('clearing synced recordings re-reads the storage snapshot afterwards', () async {
    final s = subject();

    await s.actions.synced();

    // Order is the whole point: a read taken before the clear returns the
    // pre-clear numbers, which is the stale reading users were left looking at.
    expect(s.calls, ['clear synced', 'refresh']);
  });

  test('clearing pending recordings re-reads the storage snapshot afterwards', () async {
    final s = subject();

    await s.actions.pending();

    expect(s.calls, ['clear pending', 'refresh']);
  });

  test('clearing every recording re-reads the storage snapshot afterwards', () async {
    final s = subject();

    await s.actions.all();

    expect(s.calls, ['clear all', 'refresh']);
  });

  test('each action clears only its own category', () async {
    final s = subject();

    await s.actions.pending();

    expect(s.calls, isNot(contains('clear synced')));
    expect(s.calls, isNot(contains('clear all')));
  });

  test('the storage snapshot is re-read even when the clear fails part-way', () async {
    final s = subject(
      clearPending: () async => throw StateError('device dropped the connection mid-delete'),
    );

    await expectLater(s.actions.pending(), throwsStateError);

    // A clear that failed part-way still deleted some files, so the snapshot on
    // screen is wrong in exactly the same way. The failure still surfaces.
    expect(s.calls, ['refresh']);
  });
}
