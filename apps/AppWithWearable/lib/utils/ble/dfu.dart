import 'package:flutter/foundation.dart';
import 'package:nordic_dfu/nordic_dfu.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/connect.dart';

Future<void> startDfu(BTDeviceStruct btDevice, String firmwareFile,
    {bool fileInAssets = false}) async {
  bleDisconnectDevice(btDevice);
  await Future.delayed(const Duration(seconds: 2));
  NordicDfu dfu = NordicDfu();
  await dfu.startDfu(
    btDevice.id,
    firmwareFile,
    fileInAsset: fileInAssets,
    numberOfPackets: 8,
    enableUnsafeExperimentalButtonlessServiceInSecureDfu: true,
    iosSpecialParameter: const IosSpecialParameter(
      packetReceiptNotificationParameter: 8,
      forceScanningForNewAddressInLegacyDfu: true,
      connectionTimeout: 60,
    ),
    androidSpecialParameter: const AndroidSpecialParameter(
      packetReceiptNotificationsEnabled: true,
      rebootTime: 1000,
    ),
    onProgressChanged: (deviceAddress, percent, speed, avgSpeed, currentPart, partsTotal) => debugPrint('deviceAddress: $deviceAddress, percent: $percent'),
    onError: (deviceAddress, error, errorType, message) => debugPrint('deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message'),
    onDeviceConnecting: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDeviceConnecting'),
    onDeviceConnected: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDeviceConnected'),
    onDfuProcessStarting: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarting'),
    onDfuProcessStarted: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarted'),
    onEnablingDfuMode: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onEnablingDfuMode'),
    onFirmwareValidating: (deviceAddress) => debugPrint('address: $deviceAddress, onFirmwareValidating'),
    onDfuCompleted: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDfuCompleted'),
  );
}
