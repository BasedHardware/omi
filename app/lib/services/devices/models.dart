import 'dart:async';
import 'dart:typed_data';

import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/errors.dart';
import 'package:omi/utils/logger.dart';

class OrientedImage {
  final Uint8List imageBytes;
  final ImageOrientation orientation;

  OrientedImage({required this.imageBytes, required this.orientation});
}

const String omiServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';

const String audioDataStreamCharacteristicUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
const String audioCodecCharacteristicUuid = '19b10002-e8f2-537e-4f6c-d104768a1214';

const String buttonServiceUuid = '23ba7924-0000-1000-7450-346eac492e92';
const String buttonTriggerCharacteristicUuid = '23ba7925-0000-1000-7450-346eac492e92';

const String imageDataStreamCharacteristicUuid = '19b10005-e8f2-537e-4f6c-d104768a1214';
const String imageCaptureControlCharacteristicUuid = '19b10006-e8f2-537e-4f6c-d104768a1214';

const String storageDataStreamServiceUuid = '30295780-4301-eabd-2904-2849adfeae43';
const String storageDataStreamCharacteristicUuid = '30295781-4301-eabd-2904-2849adfeae43';
const String storageReadControlCharacteristicUuid = '30295782-4301-eabd-2904-2849adfeae43';
const String storageWifiCharacteristicUuid = '30295783-4301-eabd-2904-2849adfeae43';

const String accelDataStreamServiceUuid = '32403790-0000-1000-7450-bf445e5829a2';
const String accelDataStreamCharacteristicUuid = '32403791-0000-1000-7450-bf445e5829a2';

const String batteryServiceUuid = '0000180f-0000-1000-8000-00805f9b34fb';
const String batteryLevelCharacteristicUuid = '00002a19-0000-1000-8000-00805f9b34fb';

const String speakerDataStreamServiceUuid = 'cab1ab95-2ea5-4f4d-bb56-874b72cfc984';
const String speakerDataStreamCharacteristicUuid = 'cab1ab96-2ea5-4f4d-bb56-874b72cfc984';

const String deviceInformationServiceUuid = '0000180a-0000-1000-8000-00805f9b34fb';
const String modelNumberCharacteristicUuid = '00002a24-0000-1000-8000-00805f9b34fb';
const String firmwareRevisionCharacteristicUuid = '00002a26-0000-1000-8000-00805f9b34fb';
const String hardwareRevisionCharacteristicUuid = '00002a27-0000-1000-8000-00805f9b34fb';
const String manufacturerNameCharacteristicUuid = '00002a29-0000-1000-8000-00805f9b34fb';

const String frameServiceUuid = "7A230001-5475-A6A4-654C-8431F6AD49C4";

const String plaudServiceUuid = "00001910-0000-1000-8000-00805f9b34fb";
const String plaudWriteCharUuid = "00002bb1-0000-1000-8000-00805f9b34fb";
const String plaudNotifyCharUuid = "00002bb0-0000-1000-8000-00805f9b34fb";

const String beeServiceUuid = "03d5d5c4-a86c-11ee-9d89-8f2089a49e7e";

const String fieldyServiceUuid = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";

const String friendPendantServiceUuid = "1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da";
const String friendPendantAudioCharacteristicUuid = "01000000-1111-1111-1111-111111111111";

const String limitlessServiceUuid = "632de001-604c-446b-a80f-7963e950f3fb";
const String limitlessTxCharUuid = "632de002-604c-446b-a80f-7963e950f3fb";
const String limitlessRxCharUuid = "632de003-604c-446b-a80f-7963e950f3fb";

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
