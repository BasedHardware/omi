import 'dart:async';
import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/services/devices/errors.dart';
import 'package:friend_private/utils/logger.dart';

const String friendServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';

const String audioDataStreamCharacteristicUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
const String audioCodecCharacteristicUuid = '19b10002-e8f2-537e-4f6c-d104768a1214';

const String buttonDataStreamCharacteristicUuid = '23ba7924-0000-1000-7450-346eac492e92';
const String buttonTriggerCharacteristicUuid = '23ba7925-0000-1000-7450-346eac492e92';

const String imageDataStreamCharacteristicUuid = '19b10005-e8f2-537e-4f6c-d104768a1214';
const String imageCaptureControlCharacteristicUuid = '19b10006-e8f2-537e-4f6c-d104768a1214';

const String storageDataStreamServiceUuid = '30295780-4301-eabd-2904-2849adfeae43';
const String storageDataStreamCharacteristicUuid = '30295781-4301-eabd-2904-2849adfeae43';
const String storageReadControlCharacteristicUuid = '30295782-4301-eabd-2904-2849adfeae43';

const String accelDataStreamServiceUuid = '32403790-0000-1000-7450-bf445e5829a2';
const String accelDataStreamCharacteristicUuid = '32403791-0000-1000-7450-bf445e5829a2';

const String batteryServiceUuid = '0000180f-0000-1000-8000-00805f9b34fb';
const String batteryLevelCharacteristicUuid = '00002a19-0000-1000-8000-00805f9b34fb';

const String deviceInformationServiceUuid = '0000180a-0000-1000-8000-00805f9b34fb';
const String modelNumberCharacteristicUuid = '00002a24-0000-1000-8000-00805f9b34fb';
const String firmwareRevisionCharacteristicUuid = '00002a26-0000-1000-8000-00805f9b34fb';
const String hardwareRevisionCharacteristicUuid = '00002a27-0000-1000-8000-00805f9b34fb';
const String manufacturerNameCharacteristicUuid = '00002a29-0000-1000-8000-00805f9b34fb';

const String frameServiceUuid = "7A230001-5475-A6A4-654C-8431F6AD49C4";

enum DeviceType {
  necklace,
  frame,
  watch,
}

class BtDevice {
  final String id;
  final String name;
  final DeviceType type;

  const BtDevice({
    required this.id,
    required this.name,
    required this.type,
  });

  factory BtDevice.fromScanResult(ScanResult result) {
    // Determine device type from services
    DeviceType type;
    if (result.advertisementData.serviceUuids.contains(friendServiceUuid)) {
      type = DeviceType.necklace;
    } else if (result.advertisementData.serviceUuids.contains(frameServiceUuid)) {
      type = DeviceType.frame;
    } else {
      type = DeviceType.watch;
    }

    return BtDevice(
      id: result.device.remoteId.str,
      name: result.device.platformName,
      type: type,
    );
  }

  factory BtDevice.watch() {
    return const BtDevice(
      id: 'apple_watch',
      name: 'Apple Watch',
      type: DeviceType.watch,
    );
  }
}

Future<List<BluetoothService>> getBleServices(String deviceId) async {
  final device = BluetoothDevice.fromId(deviceId);
  try {
    // Check if the device is connected before discovering services
    if (device.isDisconnected) {
      Logger.handle(Exception('Device is not connected'), StackTrace.current,
          message: 'Looks like the device is not connected. Please make sure the device is connected and try again.');
      return [];
    } else {
      // TODO: need to be fixed for open glass
      // if (Platform.isAndroid && device.servicesList.isNotEmpty) return device.servicesList;
      if (device.servicesList.isNotEmpty) return device.servicesList;
      return await device.discoverServices();
    }
  } catch (e, stackTrace) {
    logCrashMessage('Get BLE services', deviceId, e, stackTrace);
    return [];
  }
}

Future<BluetoothService?> getServiceByUuid(String deviceId, String uuid) async {
  final services = await getBleServices(deviceId);
  return services.firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == uuid);
}

BluetoothCharacteristic? getCharacteristicByUuid(BluetoothService service, String uuid) {
  return service.characteristics.firstWhereOrNull(
    (characteristic) => characteristic.uuid.str128.toLowerCase() == uuid.toLowerCase(),
  );
}
