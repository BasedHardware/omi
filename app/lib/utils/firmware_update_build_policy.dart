import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Firmware-update capabilities that differ between the standard app and the
/// Ray-Ban DAT build.
///
/// MWDATCore embeds SwiftProtobuf, so the DAT build intentionally omits the
/// native mcumgr plugin used for Omi pendant firmware updates. OpenGlass uses
/// its independent Wi-Fi OTA path and remains available in both builds.
class FirmwareUpdateBuildPolicy {
  const FirmwareUpdateBuildPolicy({required this.rayBanDat});

  static const current = FirmwareUpdateBuildPolicy(rayBanDat: bool.fromEnvironment('OMI_RAYBAN_DAT'));

  final bool rayBanDat;

  bool get allowsOmiFirmwareUpdate => !rayBanDat;

  bool get allowsOpenGlassFirmwareUpdate => true;

  bool allowsFirmwareUpdate({required bool isOpenGlass}) {
    return isOpenGlass ? allowsOpenGlassFirmwareUpdate : allowsOmiFirmwareUpdate;
  }

  bool isOpenGlassDevice(BtDevice? device) {
    if (device == null) return false;
    if (device.type == DeviceType.openglass) return true;
    if (device.type != DeviceType.omi) return false;

    final name = device.name.toLowerCase();
    return name.contains('openglass') || name.contains('omiglass') || name.contains('glass');
  }

  bool allowsFirmwareUpdateForDevice(BtDevice? device) {
    if (device?.type == DeviceType.raybanMeta) return false;
    return allowsFirmwareUpdate(isOpenGlass: isOpenGlassDevice(device));
  }
}
