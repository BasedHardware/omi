import 'dart:io';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:version/version.dart';
import 'package:package_info_plus/package_info_plus.dart';

class DeviceUtils {
  static Future<(String, bool, String)> shouldUpdateFirmware({
    required String currentFirmware,
    required Map latestFirmwareDetails,
  }) async {
    Version currentVersion = Version.parse(currentFirmware);
    if (latestFirmwareDetails.isEmpty) {
      return ('Latest Version Not Available', false, '');
    }
    if (latestFirmwareDetails.isEmpty || latestFirmwareDetails['version'] == null) {
      return ('Latest Version Not Available', false, '');
    }
    if (latestFirmwareDetails['version'] == null || latestFirmwareDetails['draft']) {
      return ('Latest Version Not Available', false, '');
    }

    String latestVersionStr = latestFirmwareDetails['version'];
    Version latestVersion = Version.parse(latestVersionStr);
    Version minVersion = Version.parse(latestFirmwareDetails['min_version']);

    if (currentVersion < minVersion) {
      return ('0', false, latestVersionStr);
    } else {
      if (latestVersion > currentVersion) {
        PackageInfo packageInfo = await PackageInfo.fromPlatform();
        if (Version.parse(packageInfo.version) <= Version.parse(latestFirmwareDetails['min_app_version']) &&
            int.parse(packageInfo.buildNumber) < int.parse(latestFirmwareDetails['min_app_version_code'])) {
          return (
            'The latest version of firmware is not compatible with this version of App (${packageInfo.version}+${packageInfo.buildNumber}). Please update the app from ${Platform.isAndroid ? 'Play Store' : 'App Store'}',
            false,
            latestVersionStr
          );
        } else {
          return ('A new version is available! Update your Omi now.', true, latestVersionStr);
        }
      } else {
        return ('You are already on the latest version', false, latestVersionStr);
      }
    }
  }

  /// Get device image path by device type and model number (most accurate)
  /// Falls back to device name if type/model not available
  static String getDeviceImagePath({
    DeviceType? deviceType,
    String? modelNumber,
    String? deviceName,
  }) {
    // Check deviceType first
    if (deviceType != null) {
      switch (deviceType) {
        case DeviceType.limitless:
          return Assets.images.limitless.path;
        case DeviceType.bee:
          return Assets.images.beeDevice.path;
        case DeviceType.openglass:
          return Assets.images.omiGlass.path;
        case DeviceType.frame:
          return Assets.images.omiDevkitWithoutRope.path;
        case DeviceType.appleWatch:
          return Assets.images.appleWatch.path;
        case DeviceType.plaud:
          return Assets.images.plaudNotePin.path;
        case DeviceType.fieldy:
          return Assets.images.fieldy.path;
        case DeviceType.friendPendant:
          return Assets.images.friendPendant.path;
        case DeviceType.omi:
          // For omi type, need to check model/name to distinguish between devkit and regular omi
          if (modelNumber != null && modelNumber.isNotEmpty && modelNumber.toUpperCase() != 'UNKNOWN') {
            final upperModel = modelNumber.toUpperCase();

            if (upperModel.contains('GLASS')) {
              return Assets.images.omiGlass.path;
            }

            if (upperModel.contains('DEVKIT') || (upperModel.contains('FRIEND'))) {
              return Assets.images.omiDevkitWithoutRope.path;
            }

            if (upperModel.contains('NEO')) {
              return Assets.images.neoOne.path;
            }
          }
          if (deviceName != null && deviceName.isNotEmpty) {
            final upperName = deviceName.toUpperCase();

            if (upperName.contains('GLASS')) {
              return Assets.images.omiGlass.path;
            }

            if (upperName.contains('DEVKIT') || upperName.contains('DEV') || (upperName.contains('FRIEND'))) {
              return Assets.images.omiDevkitWithoutRope.path;
            }

            if (upperName.contains('NEO')) {
              return Assets.images.neoOne.path;
            }
          }
          // Default omi image
          return Assets.images.omiWithoutRope.path;
      }
    }

    // Then check modelNumber for specific variants
    if (modelNumber != null && modelNumber.isNotEmpty && modelNumber.toUpperCase() != 'UNKNOWN') {
      final upperModel = modelNumber.toUpperCase();

      if (upperModel.contains('PLAUD')) {
        return Assets.images.plaudNotePin.path;
      }
      if (upperModel.contains('FRIEND PENDANT')) {
        return Assets.images.friendPendant.path;
      }
      if (upperModel.contains('OMI DEVKIT 2') || upperModel.contains('FRIEND')) {
        return Assets.images.omiDevkitWithoutRope.path;
      }
      if (upperModel.contains('GLASS')) {
        return Assets.images.omiGlass.path;
      }
      if (upperModel.contains('FRAME')) {
        return Assets.images.omiDevkitWithoutRope.path;
      }
      if (upperModel.contains('BEE')) {
        return Assets.images.beeDevice.path;
      }
      if (upperModel.contains('WATCH')) {
        return Assets.images.appleWatch.path;
      }
      if (upperModel.contains('FIELDY') || upperModel.contains('COMPASS')) {
        return Assets.images.fieldy.path;
      }
      if (upperModel.contains('NEO')) {
        return Assets.images.neoOne.path;
      }
    }

    // Fallback to device name
    if (deviceName != null && deviceName.isNotEmpty) {
      final upperName = deviceName.toUpperCase();

      if (upperName.contains('PLAUD')) {
        return Assets.images.plaudNotePin.path;
      }
      if (upperName.contains('GLASS')) {
        return Assets.images.omiGlass.path;
      }
      if (upperName.startsWith('FRIEND_')) {
        return Assets.images.friendPendant.path;
      }
      if (upperName.contains('OMI DEVKIT') || upperName.contains('OMI DEV') || upperName.contains('FRIEND')) {
        return Assets.images.omiDevkitWithoutRope.path;
      }
      if (upperName.contains('BEE')) {
        return Assets.images.beeDevice.path;
      }
      if (upperName.contains('WATCH')) {
        return Assets.images.appleWatch.path;
      }
      if (upperName.contains('FIELDY') || upperName.contains('COMPASS')) {
        return Assets.images.fieldy.path;
      }
      if (upperName.contains('LIMITLESS')) {
        return Assets.images.limitless.path;
      }
      if (upperName.contains('NEO')) {
        return Assets.images.neoOne.path;
      }
    }

    // Default
    return Assets.images.omiWithoutRope.path;
  }

  /// Convenience method when you have a BtDevice object
  static String getDeviceImageFromBtDevice(BtDevice device) {
    return getDeviceImagePath(
      deviceType: device.type,
      modelNumber: device.modelNumber,
      deviceName: device.name,
    );
  }

  /// Get device image with connection state (for special cases like Omi)
  static String getDeviceImagePathWithState({
    DeviceType? deviceType,
    String? modelNumber,
    String? deviceName,
    required bool isConnected,
  }) {
    // Special case for Omi when disconnected
    if (deviceType == DeviceType.omi && !isConnected) {
      return Assets.images.omiWithoutRopeTurnedOff.path;
    }

    // Special case for Friend Pendant when disconnected
    if (deviceType == DeviceType.friendPendant && !isConnected) {
      return Assets.images.friendPendant.path;
    }

    return getDeviceImagePath(
      deviceType: deviceType,
      modelNumber: modelNumber,
      deviceName: deviceName,
    );
  }

  /// Legacy method - kept for backwards compatibility
  @Deprecated('Use getDeviceImagePath with deviceType parameter')
  static String getDeviceImagePathByModel(String? deviceModel) {
    return getDeviceImagePath(deviceName: deviceModel);
  }
}
