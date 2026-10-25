import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/device_provider.dart';

void main() {
  group('Limitless offline-data detection', () {
    test('counts a valid pending flash-page range even on 1.x firmware', () {
      expect(
        DeviceProvider.countLimitlessPendingFlashPages({
          'oldest_flash_page': 100,
          'newest_flash_page': 2500,
          'free_capture_pages': 0,
        }),
        2401,
      );
    });

    test('rejects absent and reversed storage ranges', () {
      expect(DeviceProvider.countLimitlessPendingFlashPages(null), 0);
      expect(
        DeviceProvider.countLimitlessPendingFlashPages({
          'oldest_flash_page': 2500,
          'newest_flash_page': 100,
        }),
        0,
      );
    });
  });
}
