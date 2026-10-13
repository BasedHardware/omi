import 'package:omi/utils/analytics/registry/events.g.dart';

/// Closed reasons `OmiBleManager.startScan` reports before it scans.
/// `no_adapter` and `scanner_unavailable` stay distinct from radio-off so the
/// funnel can see those quiet returns. The user-facing copy can still match
/// Bluetooth off.
DevicePairingBlockedReason? pairingBlockFromNativeScan(String reason) {
  return switch (reason) {
    'nearby_devices_denied' => DevicePairingBlockedReason.nearbyDevicesDenied,
    'bluetooth_off' => DevicePairingBlockedReason.bluetoothOff,
    'no_adapter' => DevicePairingBlockedReason.noAdapter,
    'scanner_unavailable' => DevicePairingBlockedReason.scannerUnavailable,
    _ => null,
  };
}

/// Block that stops a Connect scan before native discovery starts.
/// Android 12+ runtime Bluetooth denial is the Nearby devices prompt.
/// Android 11 and older still need location. iOS denial is Bluetooth.
DevicePairingBlockedReason? pairingBlockBeforeScan({
  required bool isAndroid,
  required int androidSdk,
  required bool bluetoothGranted,
  required bool locationGranted,
  required bool adapterOff,
}) {
  if (!bluetoothGranted) {
    if (isAndroid && androidSdk >= 31) return DevicePairingBlockedReason.nearbyDevicesDenied;
    return DevicePairingBlockedReason.bluetoothPermissionDenied;
  }
  if (isAndroid && androidSdk > 0 && androidSdk <= 30 && !locationGranted) {
    return DevicePairingBlockedReason.locationPermissionMissing;
  }
  if (adapterOff) return DevicePairingBlockedReason.bluetoothOff;
  return null;
}

/// Major iOS version from `systemVersion` (`"18.1.2"` → 18). Unparseable is 0.
int iosMajorVersion(String systemVersion) {
  final major = int.tryParse(systemVersion.split('.').first.trim());
  if (major == null || major < 0) return 0;
  return major;
}

const int deviceScanEmptyAfterSeconds = 10;

bool shouldReportEmptyDeviceScan({required int deviceCount}) => deviceCount == 0;

DeviceConnectFailedErrorClass classifyDeviceConnectError(Object error) {
  if (error is StateError) return DeviceConnectFailedErrorClass.initializationFailed;
  final text = error.toString().toLowerCase();
  if (text.contains('timeout')) return DeviceConnectFailedErrorClass.timeout;
  if (text.contains('bluetooth') &&
      (text.contains('off') || text.contains('unavailable') || text.contains('adapter'))) {
    return DeviceConnectFailedErrorClass.bluetoothOff;
  }
  if (text.contains('permission') || text.contains('unauthorized')) {
    return DeviceConnectFailedErrorClass.permissionDenied;
  }
  if (text.contains('not found') || text.contains('notfound')) return DeviceConnectFailedErrorClass.notFound;
  return DeviceConnectFailedErrorClass.unknown;
}
