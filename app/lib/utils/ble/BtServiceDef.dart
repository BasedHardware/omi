import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class BtServiceDef {
  final String uuid;
  final String name;

  const BtServiceDef(this.uuid, this.name);
  
  bool matchesService(BluetoothService service) {
    return service.uuid == Guid(uuid) || primaryPartOfGuid(service.uuid.toString()) == primaryPartOfGuid(uuid.toString());
  }

  static String primaryPartOfGuid(String id) {
    return id.replaceAll(':', '').split('-').first.padLeft(8, '0');
  }
}

class BtCharacteristicDef {
  final String uuid;
  final String name;
  final BtServiceDef service;

  const BtCharacteristicDef(this.uuid, this.name, this.service);

  bool matchesCharacteristic(BluetoothCharacteristic characteristic) {
    return characteristic.uuid == Guid(uuid) || BtServiceDef.primaryPartOfGuid(characteristic.uuid.toString()) == BtServiceDef.primaryPartOfGuid(uuid.toString());
  }
}