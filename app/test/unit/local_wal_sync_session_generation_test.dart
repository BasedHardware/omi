import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _MockListener implements IWalSyncListener {
  int walUpdatedCount = 0;

  @override
  void onWalUpdated() {
    walUpdatedCount++;
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

Wal _wal({required int timerStart}) => Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.pcm16,
      seconds: 30,
      status: WalStatus.miss,
      storage: WalStorage.disk,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('clearUserData mid-persist refuses onWalUpdated and does not resurrect getAllWals', () async {
    final hang = Completer<void>();
    final listener = _MockListener();
    final sync = LocalWalSyncImpl(
      listener,
      persistWals: (wals) async {
        if (!hang.isCompleted) await hang.future;
      },
    );
    final wal = _wal(timerStart: 1000);
    sync.testWals = [wal];

    final persist = sync.markWalSyncedAndPersist(wal);
    sync.clearUserData();
    expect(await sync.getAllWals(), isEmpty);

    final updatesAfterClear = listener.walUpdatedCount;
    hang.complete();
    await persist;

    expect(listener.walUpdatedCount, updatesAfterClear, reason: 'must not notify after the admitting generation moved');
    expect(await sync.getAllWals(), isEmpty, reason: 'retired disk WALs must not reappear in the successor');
  });

  test('current-generation persist after clear still publishes the new session WAL only', () async {
    final snapshots = <List<Wal>>[];
    final listener = _MockListener();
    final sync = LocalWalSyncImpl(
      listener,
      persistWals: (wals) async {
        snapshots.add(List<Wal>.of(wals));
      },
    );
    final oldWal = _wal(timerStart: 1000);
    sync.testWals = [oldWal];
    sync.clearUserData();
    expect(await sync.getAllWals(), isEmpty);

    final newWal = _wal(timerStart: 2000);
    await sync.addExternalWal(newWal, admittedGeneration: sync.sessionGeneration);

    final published = await sync.getAllWals();
    expect(published, hasLength(1));
    expect(published.single.id, newWal.id);
    expect(listener.walUpdatedCount, 1, reason: 'a current-generation write after clear still notifies');
    expect(snapshots, isNotEmpty);
    expect(
      snapshots.last.map((wal) => wal.id),
      containsAll([oldWal.id, newWal.id]),
      reason: 'saves must persist retired durable bytes plus the current session',
    );
  });

  test('WAL admitted under a previous generation is refused and does not mutate _wals', () async {
    final persistCalls = <List<Wal>>[];
    final listener = _MockListener();
    final sync = LocalWalSyncImpl(
      listener,
      persistWals: (wals) async {
        persistCalls.add(List<Wal>.of(wals));
      },
    );
    final admitted = sync.sessionGeneration;
    sync.clearUserData();
    expect(sync.testWals, isEmpty);

    final wal = _wal(timerStart: 3000);
    await sync.addExternalWal(wal, admittedGeneration: admitted);

    expect(
      sync.testWals,
      isEmpty,
      reason: 'refusing the save is not enough: a retired-session WAL must not enter the live list',
    );
    expect(await sync.getAllWals(), isEmpty);
    expect(listener.walUpdatedCount, 0);
    expect(persistCalls, isEmpty);
  });
}
