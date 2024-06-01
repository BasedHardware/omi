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
          final services = device.servicesList;

          // find the buttonless DFU service 0xFE59 and characteristic to write command 0104
          // final dfuService = services.firstWhereOrNull((service) =>
          //     service.uuid.str128.toLowerCase() ==
          //     '0000fe59-0000-1000-8000-00805f9b34fb');
          // if (dfuService != null) {
          //   var dfuControlPoint = dfuService.characteristics.firstWhereOrNull(
          //       (characteristic) =>
          //           characteristic.uuid.str128.toLowerCase() ==
          //           '8ec90001-f315-4f60-9fb8-838830daea50');
          //   if (dfuControlPoint != null) {
          //     dfuControlPoint.write([0x04, 0x01], withoutResponse: true);
          //   }
          // }

          // Find the Friend buttonless DFU service and characteristic to write command 01
          final dfuService = services.firstWhereOrNull((service) =>
              service.uuid.str128.toLowerCase() ==
              '19b10000-e8f2-537e-4f6c-d104768a1214');
          if (dfuService != null) {
            var otaUpdateStart = dfuService.characteristics.firstWhereOrNull(
                (characteristic) =>
                    characteristic.uuid.str128.toLowerCase() ==
                    '814b9b7c-25fd-4acd-8604-d28877beee6f');
            if (otaUpdateStart != null) {
              otaUpdateStart.write([0x01], withoutResponse: true);
            }
          }

          // wait 2 sec for the device to reset
          await Future.delayed(const Duration(seconds: 2));

          // use FlutterBluePlus to scan for any device that supports the Nordic
          // legacy DFU service and get the id of the first one
          await FlutterBluePlus.startScan(
              withServices: [Guid('00001530-1212-efde-1523-785feabcd123')]);

          FlutterBluePlus.scanResults.listen((results) async {
            final device = results.firstWhereOrNull(
                (result) => result.device.platformName.isNotEmpty);
            if (device != null) {
              FlutterBluePlus.stopScan();
              debugPrint('Found device: ${device.device.platformName}');
              NordicDfu dfu = NordicDfu();
              await dfu.startDfu(
                device.device.remoteId.str,
                'assets/firmware/friend.firmware.zip',
                fileInAsset: true,
                forceDfu: true,
                numberOfPackets: 8,
                enableUnsafeExperimentalButtonlessServiceInSecureDfu: true,
                iosSpecialParameter: const IosSpecialParameter(
                  packetReceiptNotificationParameter: 8,
                  forceScanningForNewAddressInLegacyDfu: true,
                ),
                onProgressChanged: (
                  deviceAddress,
                  percent,
                  speed,
                  avgSpeed,
                  currentPart,
                  partsTotal,
                ) {
                  debugPrint(
                      'deviceAddress: $deviceAddress, percent: $percent');
                },
                onError: (deviceAddress, error, errorType, message) {
                  debugPrint(
                      'deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message');
                },
                onDeviceConnecting: (address) =>
                    debugPrint('onDeviceConnecting'),
                onDeviceConnected: (address) => debugPrint('onDeviceConnected'),
                onDfuProcessStarting: (address) =>
                    debugPrint('onDfuProcessStarting'),
                onDfuProcessStarted: (address) =>
                    debugPrint('onDfuProcessStarted'),
                onEnablingDfuMode: (address) => debugPrint('onEnablingDfuMode'),
              );
            }
          });
        },
        child: const Text(
          'Update Firmware',
          style: TextStyle(
              decoration: TextDecoration.underline,
              color: Colors.white,
              fontSize: 15),
        ));
  }
}
