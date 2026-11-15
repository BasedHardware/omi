import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _CountedWal extends Wal {
  _CountedWal(int start)
      : super(
            timerStart: start,
            codec: BleAudioCodec.opus,
            seconds: 30,
            status: WalStatus.synced,
            storage: WalStorage.disk);
  int reads = 0;
  @override
  WalStatus get status {
    reads++;
    return super.status;
  }
}

class _Syncs {
  _Syncs(this.rows);
  final List<Wal> rows;
  Future<List<Wal>> getAllWals() async => rows;
}

class _Service implements IWalService {
  _Service(this.syncs);
  final _Syncs syncs;
  @override
  dynamic getSyncs() => syncs;
  @override
  void subscribe(IWalServiceListener subscription, Object context) {}
  @override
  void unsubscribe(Object context) {}
  @override
  void start() {}
  @override
  Future<void> stop() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
  });
  test('selectors share one derived revision; status mutations are visible after refresh', () async {
    final rows = List.generate(1000, (i) => _CountedWal(1700000000 + i));
    rows.last.status = WalStatus.miss;
    final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async =>
            throw StateError('no uploads in view test'));
    final p = SyncProvider(walService: _Service(_Syncs(rows)), uploadGate: gate, startBackgroundSync: false);
    addTearDown(p.dispose);
    await p.initialized;
    final views = p.derivedWals;
    final syncing = p.pendingSyncWals;
    final daily = p.pendingSecondsByDay;
    for (final w in rows) {
      w.reads = 0;
    }
    for (var i = 0; i < 100; i++) {
      p.notifyListeners();
      expect(p.syncingWalsCount, 0);
      expect(p.syncedWalsCount, 999);
      expect(p.waitingWalsCount, 1);
      expect(p.needsAttentionWalsCount, 0);
      expect(p.terminallyFailedWalsCount, 0);
      expect(p.retryingWalsCount, 0);
      expect(p.uploadedWals, isEmpty);
      expect(p.refusalSummary.count, 0);
      expect(identical(p.pendingSyncWals, syncing), isTrue);
      expect(identical(p.pendingSecondsByDay, daily), isTrue);
      expect(identical(p.derivedWals, views), isTrue);
    }
    expect(rows.fold<int>(0, (n, w) => n + w.reads), 0, reason: 'progress/selectors never scan history');
    rows.last.status = WalStatus.uploaded;
    await p.refreshWals();
    expect(rows.take(rows.length - 1).fold<int>(0, (n, w) => n + w.reads), 0,
        reason: 'one in-place mutation never revisits the unchanged history');
    expect(p.pendingSyncWals, isEmpty);
    expect(p.uploadedWals, [rows.last]);
    expect(p.pendingSecondsByDay.values.single, 30);
    expect(identical(p.derivedWals, views), isTrue);
  });
}
