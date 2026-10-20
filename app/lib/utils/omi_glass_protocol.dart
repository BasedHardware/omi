import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Whether an Omi-family device should use the OmiGlass connection and OTA
/// paths. User-renamable Omi CV1 pendants must not be classified from their
/// display name alone (a name like "Kitchen Glass Omi" is not OmiGlass).
class OmiGlassProtocol {
  OmiGlassProtocol._();

  static bool usesOmiGlassProtocol(BtDevice? device) {
    if (device == null) return false;
    if (device.type == DeviceType.openglass) return true;
    if (device.type != DeviceType.omi) return false;

    if (device.omiRenamable == true) return false;
    if (device.omiOpenGlassImageStream == true) return true;

    final name = device.name.toLowerCase();
    return name.contains('openglass') || name.contains('omiglass') || name.contains('glass');
  }
}
