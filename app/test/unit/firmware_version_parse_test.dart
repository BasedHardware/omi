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

  test('firmware below the minimum still reports the zero sentinel', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(
      currentFirmware: '0.9.0',
      latestFirmwareDetails: valid,
    );

    expect(result.$1, '0');
    expect(result.$2, isFalse);
  });

  test('an up to date device is told so', () async {
    final result = await DeviceUtils.shouldUpdateFirmware(currentFirmware: '2.0.0', latestFirmwareDetails: valid);

    expect(result.$1, 'You are already on the latest version');
    expect(result.$2, isFalse);
  });
}
