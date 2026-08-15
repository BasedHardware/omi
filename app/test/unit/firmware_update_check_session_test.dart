import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/firmware_update_check_session.dart';

void main() {
  test('reconnecting the same device rejects an in-flight firmware result', () async {
    final guard = FirmwareUpdateCheckSessionGuard()..start('device-a');
    final firstSession = guard.capture()!;
    final resultReady = Completer<void>();

    final canApplyResult = () async {
      expect(guard.isCurrent(firstSession), isTrue);
      await resultReady.future;
      return guard.isCurrent(firstSession);
    }();

    guard
      ..invalidate()
      ..start('device-a');
    resultReady.complete();

    expect(await canApplyResult, isFalse);
    expect(guard.isCurrent(guard.capture()!), isTrue);
  });

  test('disconnect while device setup awaits rejects its continuation', () async {
    final guard = FirmwareUpdateCheckSessionGuard()..start('device-a');
    final setupSession = guard.capture()!;
    final setupReady = Completer<void>();

    final canContinueSetup = () async {
      await setupReady.future;
      return guard.isCurrent(setupSession);
    }();

    guard.invalidate();
    setupReady.complete();

    expect(await canContinueSetup, isFalse);
  });
}
