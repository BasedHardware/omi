import 'dart:async';
import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/utils/ble/errors.dart';



Future<List<BluetoothService>> getBleServices(String deviceId) async {
  final device = BluetoothDevice.fromId(deviceId);
  try {
    // TODO: need to be fixed for open glass
    // if (Platform.isAndroid && device.servicesList.isNotEmpty) return device.servicesList;
    return await device.discoverServices();
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
