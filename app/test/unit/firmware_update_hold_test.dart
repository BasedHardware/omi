import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/firmware_update_hold.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('holds only the release that did not install, for that pendant', () async {
    final holds = await FirmwareUpdateHold.load();
    await holds.hold(deviceId: 'pendant-a', version: '3.0.25');

    expect(holds.isHeld(deviceId: 'pendant-a', version: '3.0.25'), isTrue);
    expect(holds.isHeld(deviceId: 'pendant-a', version: 'v3.0.25'), isTrue);
    expect(holds.isHeld(deviceId: 'pendant-a', version: '3.0.26'), isFalse, reason: 'a newer release is offered');
    expect(holds.isHeld(deviceId: 'pendant-b', version: '3.0.25'), isFalse, reason: 'another pendant is not held');
  });

  test('survives a reload and is cleared by a successful install', () async {
    await (await FirmwareUpdateHold.load()).hold(deviceId: 'pendant-a', version: '3.0.25');
    final reloaded = await FirmwareUpdateHold.load();
    expect(reloaded.heldVersion('pendant-a'), '3.0.25');

    await reloaded.clear('pendant-a');
    expect((await FirmwareUpdateHold.load()).heldVersion('pendant-a'), isNull);
  });

  test('a later hold replaces the earlier one for the same pendant', () async {
    final holds = await FirmwareUpdateHold.load();
    await holds.hold(deviceId: 'pendant-a', version: '3.0.25');
    await holds.hold(deviceId: 'pendant-a', version: '3.0.26');
    expect(holds.isHeld(deviceId: 'pendant-a', version: '3.0.25'), isFalse);
    expect(holds.isHeld(deviceId: 'pendant-a', version: '3.0.26'), isTrue);
  });

  test('ignores empty identities and stays bounded', () async {
    final holds = await FirmwareUpdateHold.load();
    await holds.hold(deviceId: '', version: '3.0.25');
    await holds.hold(deviceId: 'pendant-a', version: ' ');
    expect(holds.heldVersion(''), isNull);
    expect(holds.heldVersion('pendant-a'), isNull);

    for (var i = 0; i < FirmwareUpdateHold.maxEntries + 4; i++) {
      await holds.hold(deviceId: 'pendant-$i', version: '3.0.25');
    }
    expect(holds.heldVersion('pendant-0'), isNull, reason: 'oldest entries are dropped');
    expect(holds.heldVersion('pendant-${FirmwareUpdateHold.maxEntries + 3}'), '3.0.25');
  });

  test('corrupt storage reads as no holds', () async {
    SharedPreferences.setMockInitialValues({FirmwareUpdateHold.storageKey: 'not json'});
    final holds = await FirmwareUpdateHold.load();
    expect(holds.heldVersion('pendant-a'), isNull);
    await holds.hold(deviceId: 'pendant-a', version: '3.0.25');
    expect(holds.isHeld(deviceId: 'pendant-a', version: '3.0.25'), isTrue);
  });
}
