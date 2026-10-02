import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Capture roles for the devices connected at the same time.
///
/// The app keeps every saved device connected (`btDevice` plus
/// `companionBtDevice`) and assigns roles from what is actually online:
///
/// * exactly one device carries **audio** — a pendant (Omi) when one is
///   connected, otherwise the camera device itself (OmiGlass has a mic);
/// * the camera device, when connected, carries **photos**.
///
/// Both feed the same `/v4/listen` socket, so an Omi + OmiGlass session produces
/// one multi-modal conversation. Kept as pure functions so the assignment is
/// unit-testable without BLE.
class DevicePairingRoles {
  const DevicePairingRoles._();

  /// Whether [device] streams photos. OpenGlass advertises as its own type on
  /// current firmware; older builds advertise as [DeviceType.omi] with a
  /// "glass" name, so the name heuristic is the same one the connection
  /// factory uses to pick [OmiGlassConnection].
  static bool isCameraDevice(BtDevice? device) {
    if (device == null) return false;
    if (device.type == DeviceType.openglass) return true;
    if (device.type != DeviceType.omi) return false;
    final name = device.name.toLowerCase();
    return name.contains('openglass') || name.contains('omiglass') || name.contains('glass');
  }

  /// Whether [candidate] can be paired *next to* [primary] instead of replacing
  /// it: one Omi pendant plus one OmiGlass. Two pendants (or two glasses) still
  /// replace each other, as before.
  static bool canPairAsCompanion(BtDevice primary, BtDevice candidate) {
    if (primary.id.isEmpty || candidate.id.isEmpty || primary.id == candidate.id) return false;
    final primaryIsCamera = isCameraDevice(primary);
    final candidateIsCamera = isCameraDevice(candidate);
    if (primaryIsCamera == candidateIsCamera) return false;
    final pendant = primaryIsCamera ? candidate : primary;
    final glass = primaryIsCamera ? primary : candidate;
    return pendant.type == DeviceType.omi && (glass.type == DeviceType.omi || glass.type == DeviceType.openglass);
  }

  /// The device whose audio is streamed. Prefers a non-camera device so the
  /// pendant mic wins over the glasses mic when both are connected.
  static BtDevice? selectAudioDevice(Iterable<BtDevice> connected) {
    BtDevice? fallback;
    for (final device in connected) {
      if (!isCameraDevice(device)) return device;
      fallback ??= device;
    }
    return fallback;
  }

  /// The device whose camera is streamed, or null when no camera is connected.
  static BtDevice? selectPhotoDevice(Iterable<BtDevice> connected) {
    for (final device in connected) {
      if (isCameraDevice(device)) return device;
    }
    return null;
  }
}
