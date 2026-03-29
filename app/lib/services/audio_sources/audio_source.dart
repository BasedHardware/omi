import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// A single audio frame ready for WAL ingestion.
///
/// [payload] contains headerless audio bytes (source-specific headers stripped).
/// [syncKey] is used by WAL to match frames for sync tracking.
class WalFrame {
  final List<int> payload;
  final FrameSyncKey syncKey;

  WalFrame({required this.payload, required this.syncKey});
}

/// Key for matching WAL frames during sync.
/// Uses content-based equality so WAL can match frames without knowing source details.
class FrameSyncKey {
  final List<int> bytes;

  FrameSyncKey(this.bytes);

  /// BLE sync key from 3-byte firmware header [packet_id_low, packet_id_high, packet_index].
  factory FrameSyncKey.fromBleHeader(List<int> header) {
    return FrameSyncKey(List<int>.unmodifiable(header.sublist(0, 3)));
  }

  /// Phone mic sync key from monotonic frame index (0-255 wrapping).
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

  @override
  String toString() => 'FrameSyncKey(${bytes.map((b) => '0x${b.toRadixString(16).padLeft(2, '0')}').join(', ')})';
}

/// Abstract audio source that produces WAL-ready frames from raw hardware bytes.
///
/// Both phone mic and BLE device implement this abstraction, encapsulating
/// source-specific details (header format, frame size, buffering) so that
/// WAL and CaptureProvider don't need source-specific knowledge.
abstract class AudioSource {
  /// Process raw bytes from the hardware and return WAL-ready frames.
  ///
  /// For BLE: each call produces one frame (strips 3-byte firmware header).
  /// For phone mic: buffers incoming bytes and produces 320-byte PCM frames.
  /// Returns empty list if buffering (not enough data for a complete frame yet).
  List<WalFrame> processBytes(List<int> rawBytes);

  /// Get socket-ready payload from raw bytes (for WebSocket streaming).
  ///
  /// For BLE: strips firmware header (returns audio-only bytes).
  /// For phone mic: returns raw bytes unchanged (already pure audio).
  List<int> getSocketPayload(List<int> rawBytes);

  /// Flush any internally buffered bytes into frames.
  /// Called when recording stops to capture remaining partial data.
  List<WalFrame> flush();

  /// The audio codec for this source.
  BleAudioCodec get codec;

  /// Device identification for WAL metadata.
  String get deviceId;
  String get deviceModel;
}
