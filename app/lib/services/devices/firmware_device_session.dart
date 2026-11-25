// Binds loader reads to the existing Omi transport and its connection epoch.
// Never connects, scans, or reuses evidence from a replaced/reconnected peer.
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/utils/bootloader_fingerprint.dart';

/// Does not connect or scan. Only the existing live peer may supply evidence.
FirmwareDeviceSession? captureFirmwareDeviceSession(DeviceService service, String deviceId) {
  final connection = service.connectionFor(deviceId);
  if (connection == null ||
      connection.status != DeviceConnectionState.connected ||
      connection.device.id != deviceId ||
      connection.transport.deviceId != deviceId) {
    return null;
  }
  final epoch = connection.connectionEpoch;
  return FirmwareDeviceSession(
    deviceId: deviceId,
    isCurrent: () =>
        identical(service.connectionFor(deviceId), connection) &&
        connection.status == DeviceConnectionState.connected &&
        connection.connectionEpoch == epoch &&
        connection.device.id == deviceId &&
        connection.transport.deviceId == deviceId,
    readFingerprint: () async {
      if (connection is! OmiDeviceConnection) return null;
      return connection.transport
          .readCharacteristic('19b10040-e8f2-537e-4f6c-d104768a1214', '19b10043-e8f2-537e-4f6c-d104768a1214');
    },
  );
}

/// The installed-bootloader digest the connected pendant reports, or null when unknown (older
/// firmware, no live connection, or a failed read). Never inferred from the firmware version.
Future<String?> readConnectedBootloaderSha256(String deviceId) async {
  try {
    final session = captureFirmwareDeviceSession(ServiceManager.instance().device, deviceId);
    return await session?.readBootloaderSha256();
  } catch (_) {
    return null;
  }
}
