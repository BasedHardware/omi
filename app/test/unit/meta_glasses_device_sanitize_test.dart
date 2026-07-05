import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:omi/providers/meta_wearables_provider.dart';

void main() {
  group('MetaWearablesProvider.sanitizeDevices', () {
    const named = DeviceInfo(uuid: 'AAAA-1111', name: '000R', kind: DeviceKind.rayBanMeta);

    test('collapses duplicate uuids into one entry, preferring the named one', () {
      const shadow = DeviceInfo(uuid: 'AAAA-1111', name: '', kind: DeviceKind.unknown);
      final result = MetaWearablesProvider.sanitizeDevices([shadow, named]);
      expect(result, hasLength(1));
      expect(result.single.name, '000R');
    });

    test('drops identifier-named shadow entries of the same physical device', () {
      const shadow = DeviceInfo(
        uuid: 'BBBB-2222',
        name: '9A3F0C71-4E2D-4B8A-9D11-C2E5F0A6B4D8',
        kind: DeviceKind.unknown,
      );
      final result = MetaWearablesProvider.sanitizeDevices([named, shadow]);
      expect(result, hasLength(1));
      expect(result.single.name, '000R');
    });

    test('drops entries whose name is just their own uuid', () {
      const shadow = DeviceInfo(uuid: 'CCCC-3333', name: 'CCCC-3333', kind: DeviceKind.unknown);
      final result = MetaWearablesProvider.sanitizeDevices([named, shadow]);
      expect(result, hasLength(1));
      expect(result.single.name, '000R');
    });

    test('keeps a shadow-looking device when it is the only one (never hide the glasses)', () {
      const only = DeviceInfo(
        uuid: 'DDDD-4444',
        name: '9A3F0C71-4E2D-4B8A-9D11-C2E5F0A6B4D8',
        kind: DeviceKind.unknown,
      );
      final result = MetaWearablesProvider.sanitizeDevices([only]);
      expect(result, hasLength(1));
    });

    test('keeps two genuinely different named devices (multi-device)', () {
      const second = DeviceInfo(uuid: 'EEEE-5555', name: 'Eddy Ray-Ban 2', kind: DeviceKind.rayBanMeta);
      final result = MetaWearablesProvider.sanitizeDevices([named, second]);
      expect(result, hasLength(2));
    });

    test('keeps a paired-but-unlinked pair visible so its setup state can be shown', () {
      // e.g. 00CQ before its Meta AI update: paired, named, link down.
      const unlinked = DeviceInfo(
        uuid: 'FFFF-6666',
        name: '00CQ',
        kind: DeviceKind.rayBanMeta,
        linkState: DeviceLinkState.disconnected,
      );
      final result = MetaWearablesProvider.sanitizeDevices([named, unlinked]);
      expect(result, hasLength(2), reason: 'Unlinked pairs stay listed with a setup hint, not hidden.');
    });
  });

  group('MetaWearablesProvider.capturedAtFromQueueFile', () {
    test('recovers capture time from queue filename', () {
      final at = MetaWearablesProvider.capturedAtFromQueueFile('/docs/meta_glasses_photo_queue/1751500000000.jpg');
      expect(at, DateTime.fromMillisecondsSinceEpoch(1751500000000));
    });

    test('returns null for non-numeric names so send time is used instead', () {
      expect(MetaWearablesProvider.capturedAtFromQueueFile('/docs/meta_glasses_photo_queue/oops.jpg'), isNull);
    });
  });

  group('DeviceLinkState.fromRaw', () {
    test('parses wire values and defaults to unknown', () {
      expect(DeviceLinkState.fromRaw('connected'), DeviceLinkState.connected);
      expect(DeviceLinkState.fromRaw('connecting'), DeviceLinkState.connecting);
      expect(DeviceLinkState.fromRaw('disconnected'), DeviceLinkState.disconnected);
      expect(DeviceLinkState.fromRaw(null), DeviceLinkState.unknown);
      expect(DeviceLinkState.fromRaw('bogus'), DeviceLinkState.unknown);
    });
  });
}
