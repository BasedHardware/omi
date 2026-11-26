import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/device.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const packageInfoChannel = MethodChannel('dev.fluttercommunity.plus/package_info');

  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      packageInfoChannel,
      (_) async => <String, dynamic>{
        'appName': 'omi',
        'packageName': 'com.friend.ios',
        'version': '9.9.9',
        'buildNumber': '9999',
      },
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(packageInfoChannel, null);
  });

  const valid = {
    'version': '2.0.0',
    'min_version': '1.0.0',
    'draft': false,
    'min_app_version': '1.0.0',
    'min_app_version_code': '1',
  };

  test('an unreadable firmware revision reports unknown instead of throwing', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(currentFirmware: 'Unknown', latestFirmwareDetails: valid);

    expect(result.$1, 'Unable to determine current firmware version');
    expect(result.$2, isFalse);
  });

  test('a missing min_version reports unavailable instead of throwing', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(
      currentFirmware: '1.0.0',
      latestFirmwareDetails: const {'version': '2.0.0', 'draft': false},
    );

    expect(result.$1, 'Latest Version Not Available');
    expect(result.$2, isFalse);
  });

  test('a missing draft flag is treated as published', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(
      currentFirmware: '1.0.0',
      latestFirmwareDetails: const {'version': '2.0.0', 'min_version': '1.0.0'},
    );

    expect(result.$1, 'A new version is available! Update your Omi now.');
    expect(result.$2, isTrue);
    expect(result.$3, '2.0.0');
  });

  test('a newer published firmware still offers the update', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(currentFirmware: '1.5.0', latestFirmwareDetails: valid);

    expect(result.$2, isTrue);
    expect(result.$3, '2.0.0');
  });

  test('firmware below the minimum reports a below-minimum message', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(
      currentFirmware: '0.9.0',
      latestFirmwareDetails: valid,
    );

    expect(result.$1, 'Current firmware is below the minimum version required for this update');
    expect(result.$2, isFalse);
    expect(result.$3, '2.0.0');
  });

  test('an up to date device is told so', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(currentFirmware: '2.0.0', latestFirmwareDetails: valid);

    expect(result.$1, 'You are already on the latest version');
    expect(result.$2, isFalse);
  });

  // The firmware update page sends an unusable release to the failed-check state (with Try Again) and
  // an unreadable device revision to its own message, so the classification must keep them apart.
  for (final (name, details, status) in [
    ('empty answer', <String, dynamic>{}, FirmwareUpdateCheck.releaseUnavailable),
    ('draft release', {...valid, 'draft': true}, FirmwareUpdateCheck.releaseUnavailable),
    ('missing minimum version', {...valid, 'min_version': null}, FirmwareUpdateCheck.releaseUnavailable),
    ('unparsable latest version', {...valid, 'version': 'x'}, FirmwareUpdateCheck.releaseUnavailable),
    ('non-string latest version', {...valid, 'version': 123}, FirmwareUpdateCheck.releaseUnavailable),
    ('unparsable app floor', {...valid, 'min_app_version': 'x'}, FirmwareUpdateCheck.releaseUnavailable),
    ('unparsable build floor', {...valid, 'min_app_version_code': 'x'}, FirmwareUpdateCheck.releaseUnavailable),
    ('below minimum version', {...valid, 'min_version': '1.8.0'}, FirmwareUpdateCheck.firmwareTooOld),
    (
      'newer app required',
      {...valid, 'min_app_version': '99.0.0', 'min_app_version_code': '999999'},
      FirmwareUpdateCheck.appUpdateRequired
    ),
    ('older device', valid, FirmwareUpdateCheck.updateAvailable),
  ]) {
    test('$name is classified as ${status.name}', () async {
      final result = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '1.5.0', latestFirmwareDetails: details);
      expect(result.status, status);
    });
  }

  test('an unreadable revision is unknown even when the release is unusable', () async {
    final result = await DeviceUtils.checkFirmwareUpdate(currentFirmware: 'Unknown', latestFirmwareDetails: const {});
    expect(result.status, FirmwareUpdateCheck.currentVersionUnknown);
  });

  test('a device on the latest release is confirmed up to date', () async {
    final result = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '2.0.0', latestFirmwareDetails: valid);
    expect(result.status, FirmwareUpdateCheck.upToDate);
  });

  // firmware_release.yml exposes each app minimum independently (blank = omit).
  for (final (name, version, build) in [
    ('version-only floor', '99.0.0', null),
    ('build-only floor', null, '999999'),
    ('older app with a sufficient build', '99.0.0', '1'),
    ('newer app with an insufficient build', '8.0.0', '999999'),
  ]) {
    test('$name does not offer incompatible firmware', () async {
      final result = await DeviceUtils.checkFirmwareUpdate(
        currentFirmware: '1.5.0',
        latestFirmwareDetails: {...valid, 'min_app_version': version, 'min_app_version_code': build},
      );
      expect(result.status, FirmwareUpdateCheck.appUpdateRequired);
    });
  }

  for (final details in [
    {'version': '2.0.0', 'min_version': '1.0.0'},
    {...valid, 'min_app_version': '8.0.0', 'min_app_version_code': '1'},
  ]) {
    test('legacy or satisfied app minima retain an eligible offer: $details', () async {
      final result = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '1.5.0', latestFirmwareDetails: details);
      expect(result.status, FirmwareUpdateCheck.updateAvailable);
    });
  }
}
