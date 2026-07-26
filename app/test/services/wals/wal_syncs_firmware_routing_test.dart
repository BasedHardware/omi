import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/wal_syncs.dart';

// Regression: background/auto-sync discovery read firmware off the raw connect
// object, which is frequently 'Unknown'. isRingBufferFirmware('Unknown') is
// false, so ring-buffer devices (fw >= 3.0.20 — current firmware) were routed
// to the multi-file enumerator and their offline recordings were never
// enumerated, uploaded, or turned into conversations (#10033). The fix resolves
// the enriched firmware first; only the Auto Sync page used to pass it.
void main() {
  group('resolveDiscoveryFirmware', () {
    test('enriched value wins over a raw Unknown connect object', () {
      expect(WalSyncs.resolveDiscoveryFirmware('3.0.20', 'Unknown'), '3.0.20');
    });

    test('falls back to raw when enriched is Unknown/empty/null', () {
      expect(WalSyncs.resolveDiscoveryFirmware('Unknown', '3.0.20'), '3.0.20');
      expect(WalSyncs.resolveDiscoveryFirmware('', '3.0.20'), '3.0.20');
      expect(WalSyncs.resolveDiscoveryFirmware(null, '3.0.17'), '3.0.17');
    });
  });

  group('end-to-end routing decision', () {
    test('a ring-buffer device with a raw Unknown object now routes to ring', () {
      // Before the fix this classified false (raw 'Unknown') -> multi-file
      // enumerator -> recordings never discovered.
      final resolved = WalSyncs.resolveDiscoveryFirmware('3.0.20', 'Unknown');
      expect(WalSyncs.isRingBufferFirmware(resolved), isTrue);
    });

    test('older multi-file firmware still routes to storage', () {
      final resolved = WalSyncs.resolveDiscoveryFirmware('3.0.18', 'Unknown');
      expect(WalSyncs.isRingBufferFirmware(resolved), isFalse);
    });
  });
}
