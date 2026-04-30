import 'package:nooto_v2/audio/codec.dart';

/// A single audio frame ready for downstream ingestion.
class WalFrame {
  final List<int> payload;
  final FrameSyncKey syncKey;

  WalFrame({required this.payload, required this.syncKey});
}

class FrameSyncKey {
  final List<int> bytes;

  FrameSyncKey(this.bytes);

  factory FrameSyncKey.fromIndex(int index) {
    return FrameSyncKey(List<int>.unmodifiable([index & 0xFF]));
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    if (other is! FrameSyncKey) return false;
    if (bytes.length != other.bytes.length) return false;
    for (int i = 0; i < bytes.length; i++) {
      if (bytes[i] != other.bytes[i]) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hashAll(bytes);
}

/// Abstract audio source that produces WAL-ready frames from raw hardware bytes.
///
/// Phone mic and (future) BLE devices implement this so the rest of the app
/// doesn't need source-specific knowledge.
abstract class AudioSource {
  List<WalFrame> processBytes(List<int> rawBytes);
  List<int> getSocketPayload(List<int> rawBytes);
  List<WalFrame> flush();
  BleAudioCodec get codec;
  String get deviceId;
  String get deviceModel;
}
