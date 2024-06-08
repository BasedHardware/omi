import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/structs/index.dart';
import 'package:nordic_dfu/nordic_dfu.dart';

class OtaUpdateButton extends StatefulWidget {
  const OtaUpdateButton({super.key, this.btDevice});

  final BTDeviceStruct? btDevice;

  @override
  State<OtaUpdateButton> createState() => _OtaUpdateButtonState();
}

class _OtaUpdateButtonState extends State<OtaUpdateButton> {
  @override
  Widget build(BuildContext context) {
    return TextButton(
        onPressed: () async {
          final device = BluetoothDevice.fromId(widget.btDevice!.id);
          await device.disconnect();
          await Future.delayed(const Duration(seconds: 2));
          await startDfu(widget.btDevice!.id, 'assets/friend-1.0.4.zip',
              fileInAssets: true);
        },
        child: const Text(
          'Update Firmware',
          style: TextStyle(
              decoration: TextDecoration.underline,
              color: Colors.white,
              fontSize: 15),
        ));
  }

  Future<void> startDfu(String deviceId, String firmwareFile,
      {bool fileInAssets = false}) async {
    NordicDfu dfu = NordicDfu();
    await dfu.startDfu(
      deviceId,
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
      onProgressChanged: (
        deviceAddress,
        percent,
        speed,
        avgSpeed,
        currentPart,
        partsTotal,
      ) {
        debugPrint('deviceAddress: $deviceAddress, percent: $percent');
      },
      onError: (deviceAddress, error, errorType, message) {
        debugPrint(
            'deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message');
      },
      onDeviceConnecting: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onDeviceConnecting'),
      onDeviceConnected: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onDeviceConnected'),
      onDfuProcessStarting: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarting'),
      onDfuProcessStarted: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarted'),
      onEnablingDfuMode: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onEnablingDfuMode'),
      onFirmwareValidating: (deviceAddress) =>
          debugPrint('address: $deviceAddress, onFirmwareValidating'),
      onDfuCompleted: (deviceAddress) =>
          debugPrint('deviceAddress: $deviceAddress, onDfuCompleted'),
    );
  }
}
