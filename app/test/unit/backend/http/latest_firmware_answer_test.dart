import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/device.dart';
import 'package:omi/backend/schema/gen/device_speech_wire.g.dart' as wire;
import 'package:omi/utils/device.dart';

http.Response _detail(int status, String detail) => http.Response('{"detail": "$detail"}', status);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('"no suitable update" 404 means the device is up to date on the firmware page', () async {
    // Every released backend answers a pendant on the newest firmware this way.
    final answer = latestFirmwareAnswer(_detail(404, _noNewer), noNewerAsUpToDate: true);

    expect(answer, isNotNull, reason: 'not a failed check');
    final check = await DeviceUtils.checkFirmwareUpdate(currentFirmware: '3.0.21', latestFirmwareDetails: answer!);
    expect(check.status, FirmwareUpdateCheck.upToDate);
  });

  test('an unreadable device revision stays unknown even when the server says nothing is newer', () async {
    final answer = latestFirmwareAnswer(_detail(404, _noNewer), noNewerAsUpToDate: true);

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
      test(name, () {
        expect(latestFirmwareAnswer(response, noNewerAsUpToDate: true), isNull);
        expect(latestFirmwareAnswer(response), isNull);
      });
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

  group('OpenGlass and the connection check read every answer as main does', () {
    final responses = <String, http.Response?>{
      '404 no suitable update': _detail(404, _noNewer),
      '404 device not found': _detail(404, 'Device not found'),
      '404 no releases': _detail(404, 'No releases found for the repository'),
      '500': http.Response('Internal Server Error', 500),
      '503': _detail(503, 'Service Unavailable'),
      'offline': null,
      'valid Glass release': _glassRelease,
    };
    responses.forEach((name, response) {
      test(name, () async {
        final answer = latestFirmwareAnswer(response);
        final mainAnswer = _mainLatestFirmwareAnswer(response);
        expect(answer, mainAnswer);

        // DeviceProvider.shouldUpdateFirmware passes `answer ?? {}` on (device_provider.dart, no diff vs main).
        final check =
            await DeviceUtils.shouldUpdateFirmware(currentFirmware: '2.3.2', latestFirmwareDetails: answer ?? {});
        final mainCheck =
            await DeviceUtils.shouldUpdateFirmware(currentFirmware: '2.3.2', latestFirmwareDetails: mainAnswer ?? {});
        expect(check, mainCheck);
        expect(_mainGlassRelease(answer ?? {}), _mainGlassRelease(mainAnswer ?? {}));
      });
    });

    test('the "no suitable update" 404 gives Glass no release to install', () {
      final answer = latestFirmwareAnswer(_detail(404, _noNewer)) ?? {};
      expect(answer, isEmpty);
      expect(_mainGlassRelease(answer), isNull, reason: 'the OTA page gets no version or download URL');
    });

    test('a valid Glass release keeps its version, download URL and changelog', () {
      expect(_mainGlassRelease(latestFirmwareAnswer(_glassRelease)!),
          {'version': '2.4.0', 'download_url': 'https://example.test/g.zip', 'changelog': 'Faster photos\nFixes'});
    });

    test('only the CV1 firmware page asks for the up-to-date reading', () {
      for (final path in ['lib/providers/device_provider.dart', 'lib/pages/home/omiglass_ota_update.dart']) {
        final source = File(path).readAsStringSync();
        expect(source.contains('noNewerAsUpToDate'), isFalse, reason: path);
        expect(source.contains('firmwareUpToDate'), isFalse, reason: path);
        expect(source.contains('isFirmwareUpToDate'), isFalse, reason: path);
      }
      final callers = File('lib/pages/home/firmware_mixin.dart').readAsStringSync();
      expect(callers.contains('noNewerAsUpToDate: true'), isTrue);
    });
  });
}

const _noNewer = 'No suitable firmware update found for your device version.';

final _glassRelease = http.Response(
  '{"version": "v2.4.0", "min_version": "2.0.0", "min_app_version": "1.0.0", "min_app_version_code": "1", '
  '"device_type": "openglass", "zip_url": "https://example.test/g.zip", "draft": false, '
  '"ota_update_steps": [], "is_legacy_secure_dfu": false, "changelog": ["Faster photos", "Fixes"]}',
  200,
);

/// getLatestFirmwareVersion's reading on main (bf9fad6cb3): every non-200 is null.
Map? _mainLatestFirmwareAnswer(http.Response? res) {
  if (res == null || res.statusCode != 200) return null;
  return wire.GeneratedFirmwareVersionResponse.fromJson(jsonDecode(res.body) as Map<String, dynamic>).toJson();
}

/// DeviceProvider.checkFirmwareUpdates' OpenGlass release on main (unchanged here); null leaves the OTA page
/// without a release.
Map<String, dynamic>? _mainGlassRelease(Map firmwareDetails) {
  if (firmwareDetails.isEmpty) return null;
  final versionStr = firmwareDetails['version']?.toString() ?? '';
  final cleanVersion = versionStr.startsWith('v') ? versionStr.substring(1) : versionStr;
  final changelog = firmwareDetails['changelog'];
  final changelogStr = changelog is List ? changelog.join('\n') : (changelog?.toString() ?? '');
  return {'version': cleanVersion, 'download_url': firmwareDetails['zip_url'] ?? '', 'changelog': changelogStr};
}
