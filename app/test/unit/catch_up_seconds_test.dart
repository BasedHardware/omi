import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_views.dart';

Wal _uploaded(int now, {int confirmedAgo = 0, int uploadedAgo = 90000}) => Wal(
      timerStart: now - 100000,
      codec: BleAudioCodec.opus,
      seconds: 120,
      status: WalStatus.uploaded,
      storage: WalStorage.disk,
      uploadedAt: now - uploadedAgo,
      jobPendingConfirmedAt: now - confirmedAgo,
      filePath: 'synthetic.bin',
    );

void main() {
  final now = DateTime(2026, 11, 16, 12).millisecondsSinceEpoch ~/ 1000;
  int card(List<Wal> rows, int at) =>
      deviceCatchUpLocal(rows, now: DateTime.fromMillisecondsSinceEpoch(at * 1000)).pendingSeconds;
  int total(WalDerivedViews views, int at) =>
      views.pendingSecondsByDayAt(nowSeconds: at).values.fold(0, (a, b) => a + b);

  test('dead handle contributes zero without retiring the row or audio', () {
    final wal = _uploaded(now, confirmedAgo: 301);
    final views = WalDerivedViews([wal]);
    addTearDown(views.dispose);
    expect(card([wal], now), catchUpStaleHandleOff ? 120 : 0);
    expect(total(views, now), catchUpStaleHandleOff ? 120 : 0);
    expect(views.uploaded, [wal]);
    expect(wal.status, WalStatus.uploaded);
    expect(wal.filePath, 'synthetic.bin');
  });

  test('fresh confirmation and recent upload count', () {
    for (final wal in [_uploaded(now), _uploaded(now, confirmedAgo: 90000, uploadedAgo: 86400)]) {
      final views = WalDerivedViews([wal]);
      addTearDown(views.dispose);
      expect(card([wal], now), 120);
      expect(total(views, now), 120);
    }
  });

  test('cached totals decrease exactly when a handle goes stale and refresh on confirmation', () {
    final wal = _uploaded(now, confirmedAgo: 300);
    final rows = [wal];
    final views = WalDerivedViews(rows);
    addTearDown(views.dispose);
    expect(card(rows, now), 120);
    expect(total(views, now), 120);
    final later = now + 1;
    expect(card(rows, later), catchUpStaleHandleOff ? 120 : 0);
    expect(total(views, later), catchUpStaleHandleOff ? 120 : 0);
    wal.jobPendingConfirmedAt = later;
    views.refresh();
    expect(total(views, later), 120);
  });
}
