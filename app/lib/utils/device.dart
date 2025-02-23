import 'dart:io';
import 'package:version/version.dart';
import 'package:package_info_plus/package_info_plus.dart';

class DeviceUtils {
  static Future<(String, bool)> shouldUpdateFirmware({
    required String currentFirmware,
    required Map latestFirmwareDetails,
  }) async {
    Version currentVersion = Version.parse(currentFirmware);
    if (latestFirmwareDetails.isEmpty) {
      return ('Latest Version Not Available', false);
    }
    if (latestFirmwareDetails.isEmpty || latestFirmwareDetails['version'] == null) {
      return ('Latest Version Not Available', false);
    }
    if (latestFirmwareDetails['version'] == null || latestFirmwareDetails['draft']) {
      return ('Latest Version Not Available', false);
    }
    Version latestVersion = Version.parse(latestFirmwareDetails['version']);
    Version minVersion = Version.parse(latestFirmwareDetails['min_version']);
    if (currentVersion < minVersion) {
      return ('0', false);
    } else {
      if (latestVersion > currentVersion) {
        PackageInfo packageInfo = await PackageInfo.fromPlatform();
        if (Version.parse(packageInfo.version) <= Version.parse(latestFirmwareDetails['min_app_version']) &&
            int.parse(packageInfo.buildNumber) < int.parse(latestFirmwareDetails['min_app_version_code'])) {
          return (
            'The latest version of firmware is not compatible with this version of App (${packageInfo.version}+${packageInfo.buildNumber}). Please update the app from ${Platform.isAndroid ? 'Play Store' : 'App Store'}',
            false
          );
        } else {
          return ('A new version is available! Update your Omi now.', true);
        }
      } else {
        return ('You are already on the latest version', false);
      }
    }
  }
}
