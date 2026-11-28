import 'dart:io';

import 'package:package_info_plus/package_info_plus.dart';
import 'package:version/version.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';

/// Outcome of a firmware lookup that got an answer, as far as the firmware update page may claim it.
///
/// [releaseUnavailable]: the answer has no usable release (empty, draft, or a version that does not parse),
/// so it is as inconclusive as no answer. [firmwareTooOld] and [appUpdateRequired] distinguish a usable
/// release's device and app requirements so the page can explain the actual blocker. [currentVersionUnknown] is a device-side
/// failure: the paired device reported no revision or one that does not parse (e.g. the `Unknown` sentinel
/// after a failed BLE read), so no lookup can be conclusive.
enum FirmwareUpdateCheck {
  updateAvailable,
  upToDate,
  releaseUnavailable,
  firmwareTooOld,
  appUpdateRequired,
  currentVersionUnknown
}

class DeviceUtils {
  /// The firmware lookup's answer when the server has nothing newer: the device runs the latest release.
  static const Map<String, dynamic> firmwareUpToDate = {'up_to_date': true};

  static bool isFirmwareUpToDate(Map latestFirmwareDetails) => latestFirmwareDetails['up_to_date'] == true;

  /// Closed, analysis-safe hardware family used by product telemetry.
  static String analyticsHardwareFamily(BtDevice device) {
    switch (device.type) {
      case DeviceType.omi:
        final identity = '${device.modelNumber} ${device.name}'.toUpperCase();
        if (isOmiCv1(modelNumber: device.modelNumber, deviceName: device.name)) return 'omi_cv1';
        if (identity.contains('FRIEND')) return 'friend_devkit';
        if (isOmiDevKit(modelNumber: device.modelNumber, deviceName: device.name)) return 'omi_devkit';
        if (identity.contains('GLASS')) return 'omi_glass';
        if (identity.contains('NEO')) return 'omi_neo';
        return 'omi_unknown';
      case DeviceType.openglass:
        return 'omi_glass';
      case DeviceType.appleWatch:
        return 'apple_watch';
      case DeviceType.plaud:
        return 'plaud';
      case DeviceType.bee:
        return 'bee';
      case DeviceType.fieldy:
        return 'fieldy';
      case DeviceType.friendPendant:
        return 'friend_pendant';
      case DeviceType.limitless:
        return 'limitless';
      case DeviceType.raybanMeta:
        return 'rayban_meta';
    }
  }

  static Version? _tryParseVersion(Object? value) {
    if (value is! String || value.isEmpty) return null;
    try {
      return Version.parse(value);
    } catch (e) {
      return null;
    }
  }

  static bool isValidFirmwareVersion(Object? value) => _tryParseVersion(value) != null;

  static Future<(String, bool, String)> shouldUpdateFirmware({
    required String currentFirmware,
    required Map latestFirmwareDetails,
  }) async {
    final check = await checkFirmwareUpdate(
      currentFirmware: currentFirmware,
      latestFirmwareDetails: latestFirmwareDetails,
    );
    return (check.message, check.status == FirmwareUpdateCheck.updateAvailable, check.version);
  }

  /// Classifies a firmware lookup. Only [FirmwareUpdateCheck.upToDate] means the lookup confirmed the
  /// device already runs the latest release. An empty or unparsable device revision is
  /// [FirmwareUpdateCheck.currentVersionUnknown] whatever the lookup says.
  static Future<({FirmwareUpdateCheck status, String message, String version})> checkFirmwareUpdate({
    required String currentFirmware,
    required Map latestFirmwareDetails,
  }) async {
    const releaseUnavailable = FirmwareUpdateCheck.releaseUnavailable;
    Version? currentVersion = _tryParseVersion(currentFirmware);
    if (currentVersion == null) {
      return (
        status: FirmwareUpdateCheck.currentVersionUnknown,
        message: 'Unable to determine current firmware version',
        version: '',
      );
    }
    if (isFirmwareUpToDate(latestFirmwareDetails)) {
      return (
        status: FirmwareUpdateCheck.upToDate,
        message: 'You are already on the latest version',
        version: currentFirmware,
      );
    }
    if (latestFirmwareDetails.isEmpty || latestFirmwareDetails['version'] == null) {
      return (status: releaseUnavailable, message: 'Latest Version Not Available', version: '');
    }
    if (latestFirmwareDetails['draft'] == true) {
      return (status: releaseUnavailable, message: 'Latest Version Not Available', version: '');
    }

    final latestVersionValue = latestFirmwareDetails['version'];
    Version? latestVersion = _tryParseVersion(latestVersionValue);
    Version? minVersion = _tryParseVersion(latestFirmwareDetails['min_version']);
    if (latestVersion == null || minVersion == null) {
      return (status: releaseUnavailable, message: 'Latest Version Not Available', version: '');
    }
    final latestVersionStr = latestVersionValue as String;

    if (currentVersion < minVersion) {
      return (
        status: FirmwareUpdateCheck.firmwareTooOld,
        message: 'Current firmware is below the minimum version required for this update',
        version: latestVersionStr,
      );
    } else {
      if (latestVersion > currentVersion) {
        PackageInfo packageInfo = await PackageInfo.fromPlatform();
        final appVersion = _tryParseVersion(packageInfo.version);
        final minAppVersion = _tryParseVersion(latestFirmwareDetails['min_app_version']);
        final buildNumber = int.tryParse(packageInfo.buildNumber);
        final minBuildNumber = int.tryParse('${latestFirmwareDetails['min_app_version_code']}');
        // The release workflow permits either floor independently; absent floors keep legacy
        // releases eligible, while a declared but unreadable requirement is inconclusive.
        final hasVersionFloor = latestFirmwareDetails['min_app_version'] != null;
        final hasBuildFloor = latestFirmwareDetails['min_app_version_code'] != null;
        if ((hasVersionFloor && minAppVersion == null) || (hasBuildFloor && minBuildNumber == null)) {
          return (status: releaseUnavailable, message: 'Latest Version Not Available', version: '');
        }
        if ((hasVersionFloor && (appVersion == null || appVersion < minAppVersion!)) ||
            (hasBuildFloor && (buildNumber == null || buildNumber < minBuildNumber!))) {
          return (
            status: FirmwareUpdateCheck.appUpdateRequired,
            message:
                'The latest version of firmware is not compatible with this version of App (${packageInfo.version}+${packageInfo.buildNumber}). Please update the app from ${Platform.isAndroid ? 'Play Store' : 'App Store'}',
            version: latestVersionStr,
          );
        } else {
          return (
            status: FirmwareUpdateCheck.updateAvailable,
            message: 'A new version is available! Update your Omi now.',
            version: latestVersionStr,
          );
        }
      } else {
        return (
          status: FirmwareUpdateCheck.upToDate,
          message: 'You are already on the latest version',
          version: latestVersionStr,
        );
      }
    }
  }

  /// Whether an Omi-type device is a DevKit board rather than the consumer
  /// pendant. Match on `DEVKIT`/`DEV KIT` (both spellings ship, e.g.
  /// "Friend Dev Kit 1"), not a loose `DEV` — the consumer's default model
  /// fallback is `'Omi Device'`.
  static bool isOmiDevKit({String? modelNumber, String? deviceName}) {
    bool matches(String? value) {
      if (value == null || value.isEmpty) return false;
      final upper = value.toUpperCase();
      return upper.contains('DEVKIT') || upper.contains('DEV KIT');
    }

    return matches(modelNumber) || matches(deviceName);
  }

  /// Whether a [DeviceType.omi] device is the consumer CV1 pendant rather than
  /// another omi-enumerated variant (DevKit 1/2, Glass, Neo, Friend), which all
  /// report the same DeviceType. Used to scope CV1-only UI like the "How to use
  /// your Omi" button tutorial. Callers must have already checked the device is
  /// [DeviceType.omi]. CV1 reports `'Omi CV 1'` (or the `'Omi Device'` fallback
  /// when the GATT model read fails), so match by excluding the known non-CV1
  /// variants instead of allow-listing an exact CV1 string.
  ///
  /// A concrete GATT model number is authoritative — trust it and ignore the
  /// name. The generic `'Omi Device'` / `'Unknown'` fallback (reported by CV1
  /// and DevKit alike when the model read fails) is not concrete, so defer to
  /// the advertised name in that case. With neither a concrete model nor a name
  /// we can't positively identify a CV1, so return false.
  static bool isOmiCv1({String? modelNumber, String? deviceName}) {
    const nonCv1 = ['DEVKIT', 'DEV KIT', 'GLASS', 'NEO', 'FRIEND'];
    bool isVariant(String value) {
      if (value.isEmpty) return false;
      final upper = value.toUpperCase();
      return nonCv1.any(upper.contains);
    }

    final model = modelNumber?.trim() ?? '';
    final name = deviceName?.trim() ?? '';
    final upperModel = model.toUpperCase();
    final hasConcreteModel = model.isNotEmpty && upperModel != 'OMI DEVICE' && upperModel != 'UNKNOWN';

    if (hasConcreteModel) return !isVariant(model);
    if (name.isNotEmpty) return !isVariant(name);
    return false;
  }

  /// Get device image path by device type and model number (most accurate)
  /// Falls back to device name if type/model not available
  static String getDeviceImagePath({DeviceType? deviceType, String? modelNumber, String? deviceName}) {
    // Check deviceType first
    if (deviceType != null) {
      switch (deviceType) {
        case DeviceType.limitless:
          return Assets.images.limitless.path;
        case DeviceType.bee:
          return Assets.images.beeDevice.path;
        case DeviceType.openglass:
          return Assets.images.omiGlass.path;
        case DeviceType.appleWatch:
          return Assets.images.appleWatch.path;
        case DeviceType.plaud:
          return Assets.images.plaudNotePin.path;
        case DeviceType.fieldy:
          return Assets.images.fieldy.path;
        case DeviceType.friendPendant:
          return Assets.images.friendPendant.path;
        case DeviceType.raybanMeta:
          return Assets.images.raybanMeta.path;
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
    return getDeviceImagePath(deviceType: device.type, modelNumber: device.modelNumber, deviceName: device.name);
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

    return getDeviceImagePath(deviceType: deviceType, modelNumber: modelNumber, deviceName: deviceName);
  }
}
