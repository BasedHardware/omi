import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/firmware_install_verification.dart';

void main() {
  for (final (before, observed, target, expected) in [
    ('3.1.0', '3.2.0', '3.2.0', FirmwareInstallOutcome.installed),
    ('3.1.0', '3.1.1', '3.2.0', FirmwareInstallOutcome.installed),
    ('3.1.0', '3.1.0', '3.2.0', FirmwareInstallOutcome.notInstalled),
    ('3.1.0', '3.1.0', '3.1.0', FirmwareInstallOutcome.notInstalled),
    (' 3.1.0 ', '3.1.0', '3.1.0', FirmwareInstallOutcome.notInstalled),
    ('', '3.2.0', '3.2.0', FirmwareInstallOutcome.installed),
    ('unknown', '3.2.0', '3.2.0', FirmwareInstallOutcome.installed),
    (' Unknown ', '3.2.0', '3.2.0', FirmwareInstallOutcome.installed),
    ('', '3.1.0', '3.2.0', FirmwareInstallOutcome.notInstalled),
    ('unknown', '3.1.0', '3.2.0', FirmwareInstallOutcome.notInstalled),
    ('unknown', '3.1.0', null, FirmwareInstallOutcome.notInstalled),
    ('unknown', '3.1.0', 'Unknown', FirmwareInstallOutcome.notInstalled),
  ]) {
    test('fresh DIS $observed from $before with target $target yields $expected', () async {
      final device = _FakeReconnect();
      final result = verifyFirmwareInstallation(
        observations: device.reads.stream,
        deviceId: 'pendant',
        fromVersion: before,
        targetVersion: target,
      );
      device.read('other-pendant', '3.2.0');
      device.read('pendant', 'Unknown');
      device.read('pendant', ' $observed ');
      final installed = await result;
      expect(installed.outcome, expected);
      expect(installed.observedVersion, observed);
      expect(device.reads.hasListener, isFalse);
      await device.reads.close();
    });
  }

  test('no reconnect or no readable DIS is bounded at three minutes', () {
    fakeAsync((time) {
      final device = _FakeReconnect();
      FirmwareInstallResult? result;
      verifyFirmwareInstallation(
        observations: device.reads.stream,
        deviceId: 'pendant',
        fromVersion: '3.1.0',
        targetVersion: '3.2.0',
      ).then((value) => result = value);
      device.read('pendant', '');
      device.read('pendant', 'Unknown');
      time.elapse(const Duration(minutes: 3) - const Duration(milliseconds: 1));
      expect(result, isNull);
      time.elapse(const Duration(milliseconds: 1));
      expect(result!.outcome, FirmwareInstallOutcome.noReconnect);
      expect(result!.observedVersion, isNull);
      expect(device.reads.hasListener, isFalse);
      expect(time.pendingTimers, isEmpty);
      device.reads.close();
    });
  });
}

class _FakeReconnect {
  final reads = StreamController<FirmwareRevisionObservation>.broadcast(sync: true);
  void read(String id, String revision) => reads.add((deviceId: id, version: revision));
}
