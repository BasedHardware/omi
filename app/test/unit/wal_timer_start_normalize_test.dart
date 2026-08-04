import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/wals/wal.dart';

void main() {
  group('normalizeWalTimerStart (#4770)', () {
    const now = 2000000000;

    test('shifts a mildly future device window so it ends at now', () {
      // Phone shows 7:39; device RTC embedded 7:42 (+180s) for a 60s clip.
      final proposed = now + 180;
      final normalized = normalizeWalTimerStart(proposed, durationSeconds: 60, nowSeconds: now);

      expect(normalized, now - 60);
      expect(normalized + 60, now);
    });

    test('leaves a past capture window unchanged', () {
      final proposed = now - 600;
      expect(normalizeWalTimerStart(proposed, durationSeconds: 60, nowSeconds: now), proposed);
    });

    test('replaces far-future garbage with now - duration', () {
      final proposed = now + 3600;
      expect(normalizeWalTimerStart(proposed, durationSeconds: 45, nowSeconds: now), now - 45);
    });

    test('zero-duration future start clamps to now', () {
      expect(normalizeWalTimerStart(now + 30, durationSeconds: 0, nowSeconds: now), now);
    });
  });
}
