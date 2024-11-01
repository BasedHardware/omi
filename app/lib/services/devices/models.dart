import 'dart:async';
import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/services/devices/errors.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/constants.dart';
import 'package:friend_private/utils/enums.dart';

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
