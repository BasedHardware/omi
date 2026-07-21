/// Omi device BLE protocol helpers. See sdks/device/PROTOCOL.md.
library;

const String omiServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
const String audioDataUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
const String audioCodecUuid = '19b10002-e8f2-537e-4f6c-d104768a1214';
const String batteryServiceUuid = '0000180f-0000-1000-8000-00805f9b34fb';
const String batteryLevelUuid = '00002a19-0000-1000-8000-00805f9b34fb';

const int packetHeaderBytes = 3;
const int pcmSampleRateHz = 16000;
const int opusFrameSamples = 960;
const int pcmChannels = 1;

/// Strip the 3-byte Omi audio packet header.
List<int> stripPacketHeader(List<int> packet) {
  if (packet.length <= packetHeaderBytes) {
    return const <int>[];
  }
  return packet.sublist(packetHeaderBytes);
}
