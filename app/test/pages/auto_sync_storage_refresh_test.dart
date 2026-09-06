/// Clearing device recordings must re-read the device's storage snapshot.
///
/// The Sync page's storage card renders the ring-status snapshot loaded in
/// `initState`. Clearing recordings while the page stayed open deleted the files
/// but left that snapshot untouched, so the card kept reporting the device full
/// (472 MB of 472 MB used, 12 KB free) until the user navigated away and back —
/// which re-ran the page-open read and showed the true 0 B.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/auto_sync_page.dart';

void main() {
  test('the storage snapshot is re-read after the clear, not before it', () async {
    final calls = <String>[];

    await clearRecordingsThenRefreshStorage(
      clearRecordings: () async => calls.add('clear'),
      refreshDeviceStorage: () async => calls.add('refresh'),
    );

    // Order is the whole point: a read taken before the clear returns the
    // pre-clear numbers, which is the stale reading users were left looking at.
    expect(calls, ['clear', 'refresh']);
  });

  test('the storage snapshot is re-read even when the clear fails part-way', () async {
    final calls = <String>[];

    await expectLater(
      clearRecordingsThenRefreshStorage(
        clearRecordings: () async {
          calls.add('clear');
          throw StateError('device dropped the connection mid-delete');
        },
        refreshDeviceStorage: () async => calls.add('refresh'),
      ),
      throwsStateError,
    );

    // A clear that fails part-way still deleted some files, so the snapshot on
    // screen is wrong in exactly the same way. The failure still surfaces.
    expect(calls, ['clear', 'refresh']);
  });
}
