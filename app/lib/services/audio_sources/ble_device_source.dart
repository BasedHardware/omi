import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';

/// Audio source for Omi/OpenGlass BLE devices.
///
/// BLE devices prepend a 3-byte firmware header to each audio packet:
///   [packet_id_low, packet_id_high, packet_index]
///
/// This source strips the header to produce headerless audio payloads
/// and uses the header bytes as the sync key for WAL frame matching.
class BleDeviceSource implements AudioSource {
  static const int headerSize = 3;

  @override
  final BleAudioCodec codec;

  @override
  final String deviceId;

  @override
  final String deviceModel;

  /// Observes audio for presentation only; it never alters frames.
  final AudioTap? onAudio;

  BleDeviceSource({
    required this.codec,
    required this.deviceId,
    required this.deviceModel,
    this.onAudio,
  });

  @override
  List<WalFrame> processBytes(List<int> rawBytes) {
    if (rawBytes.length <= headerSize) return [];

    final payload = rawBytes.sublist(headerSize);
    onAudio?.call(payload, codec);
    return [
      WalFrame(
        payload: payload,
        syncKey: FrameSyncKey.fromBleHeader(rawBytes),
      ),
    ];
  }

  @override
  List<int> getSocketPayload(List<int> rawBytes) {
    return rawBytes.length > headerSize ? rawBytes.sublist(headerSize) : const [];
  }

  @override
  List<WalFrame> flush() => [];
}
