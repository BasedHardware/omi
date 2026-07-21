/// GATT UUIDs mirrored from the Omi Flutter app (`app/lib/services/devices/models.dart`).
library;

const String omiServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
const String audioDataStreamCharacteristicUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
const String audioCodecCharacteristicUuid = '19b10002-e8f2-537e-4f6c-d104768a1214';
const String imageDataStreamCharacteristicUuid = '19b10005-e8f2-537e-4f6c-d104768a1214';
const String imageCaptureControlCharacteristicUuid = '19b10006-e8f2-537e-4f6c-d104768a1214';

const String buttonServiceUuid = '23ba7924-0000-1000-7450-346eac492e92';
const String buttonTriggerCharacteristicUuid = '23ba7925-0000-1000-7450-346eac492e92';

const String storageDataStreamServiceUuid = '30295780-4301-eabd-2904-2849adfeae43';
const String storageDataStreamCharacteristicUuid = '30295781-4301-eabd-2904-2849adfeae43';
const String storageReadControlCharacteristicUuid = '30295782-4301-eabd-2904-2849adfeae43';

const String timeSyncServiceUuid = '19b10030-e8f2-537e-4f6c-d104768a1214';
const String timeSyncWriteCharacteristicUuid = '19b10031-e8f2-537e-4f6c-d104768a1214';
const String timeSyncReadCharacteristicUuid = '19b10032-e8f2-537e-4f6c-d104768a1214';

const String batteryServiceUuid = '0000180f-0000-1000-8000-00805f9b34fb';
const String batteryLevelCharacteristicUuid = '00002a19-0000-1000-8000-00805f9b34fb';

const String deviceInformationServiceUuid = '0000180a-0000-1000-8000-00805f9b34fb';
const String modelNumberCharacteristicUuid = '00002a24-0000-1000-8000-00805f9b34fb';
const String firmwareRevisionCharacteristicUuid = '00002a26-0000-1000-8000-00805f9b34fb';
const String hardwareRevisionCharacteristicUuid = '00002a27-0000-1000-8000-00805f9b34fb';
const String manufacturerNameCharacteristicUuid = '00002a29-0000-1000-8000-00805f9b34fb';
const String serialNumberCharacteristicUuid = '00002a25-0000-1000-8000-00805f9b34fb';

// Aliases used by multi-lang device protocol packages
const String audioDataUuid = audioDataStreamCharacteristicUuid;
const String audioCodecUuid = audioCodecCharacteristicUuid;
const String batteryLevelUuid = batteryLevelCharacteristicUuid;
