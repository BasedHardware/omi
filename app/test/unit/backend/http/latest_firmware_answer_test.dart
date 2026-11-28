import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/device.dart';
import 'package:omi/utils/device.dart';

http.Response _detail(int status, String detail) => http.Response('{"detail": "$detail"}', status);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('"no suitable update" 404 means the device is up to date', () async {
    // Every released backend answers a pendant on the newest firmware this way.
    final answer = latestFirmwareAnswer(_detail(404, 'No suitable firmware update found for your device version.'));

    expect(answer, isNotNull, reason: 'not a failed check');
    final check = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '3.0.21', latestFirmwareDetails: answer!);
    expect(check.status, FirmwareUpdateCheck.upToDate);
  });

  test('an unreadable device revision stays unknown even when the server says nothing is newer', () async {
    final answer = latestFirmwareAnswer(_detail(404, 'No suitable firmware update found for your device version.'));

    final check = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '', latestFirmwareDetails: answer!);
    expect(check.status, FirmwareUpdateCheck.currentVersionUnknown);
  });

  group('a failed check is never up to date', () {
    final failures = <String, http.Response?>{
      'offline': null,
      '500': http.Response('Internal Server Error', 500),
      '503': _detail(503, 'Service Unavailable'),
      '404 device not found': _detail(404, 'Device not found'),
      '404 no releases': _detail(404, 'No releases found for the repository'),
      '404 without a body': http.Response('', 404),
      '404 html': http.Response('<html>Not Found</html>', 404),
      '400 unreadable revision': _detail(400, 'Could not determine current firmware version'),
    };
    failures.forEach((name, response) {
      test(name, () => expect(latestFirmwareAnswer(response), isNull));
    });
  });

  test('a 200 is the release', () {
    final answer = latestFirmwareAnswer(http.Response(
      '{"version": "3.0.22", "min_version": "3.0.0", "min_app_version": "1.0.0", "min_app_version_code": "1", '
      '"device_type": "omi", "zip_url": "https://example.test/fw.zip", "draft": false, '
      '"ota_update_steps": [], "is_legacy_secure_dfu": false, "changelog": []}',
      200,
    ));
    expect(answer!['version'], '3.0.22');
  });

  group('OpenGlass OTA', () {
    const noNewer = 'No suitable firmware update found for your device version.';

    test('the "no suitable update" 404 offers no install and clears a stale offer', () async {
      final answer = latestFirmwareAnswer(_detail(404, noNewer))!;

      final check = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '2.3.2', latestFirmwareDetails: answer);
      expect(check.status, FirmwareUpdateCheck.upToDate);
      final release = DeviceUtils.openGlassOtaRelease(answer);
      expect(release, isEmpty, reason: 'the provider replaces any earlier release with nothing');
      expect(DeviceUtils.openGlassOffersUpdate(currentVersion: '2.3.2', release: release!), isFalse);
    });

    test('a release without a version or download URL offers no install', () {
      expect(DeviceUtils.openGlassOtaRelease({'version': '2.4.0', 'zip_url': ''}), isNull);
      expect(DeviceUtils.openGlassOtaRelease({'version': '', 'zip_url': 'https://example.test/g.zip'}), isNull);
      expect(DeviceUtils.openGlassOtaRelease({}), isNull, reason: 'a failed check keeps what is known');
      for (final release in [
        {'version': '', 'download_url': '', 'changelog': ''},
        {'version': '2.4.0', 'download_url': ''},
        {'version': '', 'download_url': 'https://example.test/g.zip'},
        <String, dynamic>{},
      ]) {
        expect(DeviceUtils.openGlassOffersUpdate(currentVersion: '2.3.2', release: release), isFalse,
            reason: '$release');
      }
    });

    test('a newer release with a download URL is offered', () {
      final answer = latestFirmwareAnswer(http.Response(
        '{"version": "v2.4.0", "min_version": "2.0.0", "min_app_version": "1.0.0", "min_app_version_code": "1", '
        '"device_type": "openglass", "zip_url": "https://example.test/g.zip", "draft": false, '
        '"ota_update_steps": [], "is_legacy_secure_dfu": false, "changelog": ["Faster photos", "Fixes"]}',
        200,
      ))!;

      final release = DeviceUtils.openGlassOtaRelease(answer)!;
      expect(release,
          {'version': '2.4.0', 'download_url': 'https://example.test/g.zip', 'changelog': 'Faster photos\nFixes'});
      expect(DeviceUtils.openGlassOffersUpdate(currentVersion: '2.3.2', release: release), isTrue);
      expect(DeviceUtils.openGlassOffersUpdate(currentVersion: '2.4.0', release: release), isFalse);
      expect(DeviceUtils.openGlassOffersUpdate(currentVersion: '2.5.0', release: release), isFalse);
    });
  });
}
