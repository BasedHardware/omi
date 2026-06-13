import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

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

const String timeSyncServiceUuid = '19b10030-e8f2-537e-4f6c-d104768a1214';
const String timeSyncWriteCharacteristicUuid = '19b10031-e8f2-537e-4f6c-d104768a1214';
const String timeSyncReadCharacteristicUuid = '19b10032-e8f2-537e-4f6c-d104768a1214';

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
const String serialNumberCharacteristicUuid = '00002a25-0000-1000-8000-00805f9b34fb';

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

// OmiGlass OTA Service UUIDs
const String omiGlassOtaServiceUuid = "19b10010-e8f2-537e-4f6c-d104768a1214";
const String omiGlassOtaControlCharacteristicUuid = "19b10011-e8f2-537e-4f6c-d104768a1214";
const String omiGlassOtaDataCharacteristicUuid = "19b10012-e8f2-537e-4f6c-d104768a1214";

// OmiGlass OTA Commands
const int otaCmdSetWifi = 0x01;
const int otaCmdStartOta = 0x02;
const int otaCmdCancelOta = 0x03;
const int otaCmdGetStatus = 0x04;
const int otaCmdSetUrl = 0x05;

// OmiGlass OTA Status Codes
const int otaStatusIdle = 0x00;
const int otaStatusWifiConnecting = 0x10;
const int otaStatusWifiConnected = 0x11;
const int otaStatusWifiFailed = 0x12;
const int otaStatusDownloading = 0x20;
const int otaStatusDownloadComplete = 0x21;
const int otaStatusDownloadFailed = 0x22;
const int otaStatusInstalling = 0x30;
const int otaStatusInstallComplete = 0x31;
const int otaStatusInstallFailed = 0x32;
const int otaStatusRebooting = 0x40;
const int otaStatusError = 0xFF;
