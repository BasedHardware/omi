import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/flash_page_wal_sync.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

void main() {
  group('FlashPageWalSyncImpl.classifyStall', () {
    test('newest page advanced past enumerated end means the pendant is recording', () {
      final reason = FlashPageWalSyncImpl.classifyStall(
        endPageAtEnumeration: 100,
        statusAfterStall: {'oldest_flash_page': 40, 'newest_flash_page': 130},
      );
      expect(reason, FlashSyncStallReason.recordingSuspected);
    });

    test('newest page unchanged is an unknown stall (plain transfer lull)', () {
      final reason = FlashPageWalSyncImpl.classifyStall(
        endPageAtEnumeration: 100,
        statusAfterStall: {'oldest_flash_page': 40, 'newest_flash_page': 100},
      );
      expect(reason, FlashSyncStallReason.unknown);
    });

    test('missing status stays unknown — never a recording false-positive', () {
      expect(
        FlashPageWalSyncImpl.classifyStall(endPageAtEnumeration: 100, statusAfterStall: null),
        FlashSyncStallReason.unknown,
      );
      expect(
        FlashPageWalSyncImpl.classifyStall(endPageAtEnumeration: 100, statusAfterStall: {'oldest_flash_page': 40}),
        FlashSyncStallReason.unknown,
      );
    });

    test('newest page behind enumerated end (pages ACKed away) is unknown', () {
      final reason = FlashPageWalSyncImpl.classifyStall(
        endPageAtEnumeration: 100,
        statusAfterStall: {'oldest_flash_page': 40, 'newest_flash_page': 90},
      );
      expect(reason, FlashSyncStallReason.unknown);
    });
  });
}
