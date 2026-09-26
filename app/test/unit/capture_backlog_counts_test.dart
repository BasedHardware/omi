import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Only what the backlog-count getter reads: the session's disk WALs.
class _PhoneSync {
  _PhoneSync(this.wals);

  final List<Wal> wals;

  List<Wal> getSessionWals(int sessionStartSeconds) =>
      wals.where((w) => w.storage == WalStorage.disk && w.timerStart >= sessionStartSeconds).toList();
}

class _Syncs {
  _Syncs(this.phone);

  final _PhoneSync phone;
}

class _WalService implements IWalService {
  _WalService(this.phone);

  final _PhoneSync phone;

  @override
  dynamic getSyncs() => _Syncs(phone);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

Wal _wal(int timerStart, WalStatus status) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: status,
    storage: WalStorage.disk,
    device: 'omi',
    filePath: 'backlog_$timerStart.bin',
  );
}

CaptureProvider _provider(List<Wal> wals) {
  return CaptureProvider(
    walService: _WalService(_PhoneSync(wals)),
    bleListeners: _NoopBle(),
    inProgressConversationLoader: () async {},
    localSegmentStore: LocalSegmentStore.disabled(),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('sessionTranscriptionBacklogCounts', () {
    test('counts unsynced session WALs out of the session total', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final provider = _provider([
        _wal(now - 110, WalStatus.synced),
        _wal(now - 50, WalStatus.miss),
        _wal(now - 40, WalStatus.miss),
      ]);
      provider.testSessionStartSeconds = now - 120;
      addTearDown(provider.dispose);

      expect(provider.sessionTranscriptionBacklogCounts, (pending: 2, total: 3));
    });

    test('is empty without an active session', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final provider = _provider([_wal(now - 30, WalStatus.miss)]);
      addTearDown(provider.dispose);

      expect(provider.sessionTranscriptionBacklogCounts, (pending: 0, total: 0));
    });

    test('ignores WALs recorded before the session started', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final provider = _provider([
        _wal(now - 500, WalStatus.miss),
        _wal(now - 20, WalStatus.miss),
      ]);
      provider.testSessionStartSeconds = now - 60;
      addTearDown(provider.dispose);

      expect(provider.sessionTranscriptionBacklogCounts, (pending: 1, total: 1));
    });
  });
}
