/// Omi device SDK for Flutter/Dart.
///
/// BLE UUIDs and audio framing match the main Omi app
/// (`app/lib/services/devices/models.dart`).
library;

export 'uuids.dart';
export 'ble/omi_ble.dart';
export 'ble/flutter_blue_plus_omi_ble.dart';
export 'stt/stt.dart';

const int packetHeaderBytes = 3;
const int pcmSampleRateHz = 16000;
const int opusFrameSamples = 960;
const int pcmChannels = 1;

/// Strip the 3-byte Omi audio packet header (matches Python OmiOpusDecoder).
List<int> stripPacketHeader(List<int> packet) {
  if (packet.length <= packetHeaderBytes) {
    return const <int>[];
  }
  return packet.sublist(packetHeaderBytes);
}
