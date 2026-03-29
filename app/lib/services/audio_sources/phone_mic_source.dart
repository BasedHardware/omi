import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';

/// Audio source for the phone's built-in microphone.
///
/// Phone mic records PCM16 audio at 16kHz mono. Raw bytes arrive in
/// variable-sized chunks from the platform microphone API. This source
/// buffers incoming bytes and splits them into fixed 320-byte frames
/// (10ms at 16kHz, 16-bit mono = 160 samples x 2 bytes).
///
/// Each frame gets a monotonic index (0-255 wrapping) as its sync key.
class PhoneMicSource implements AudioSource {
  /// Fixed frame size: 10ms at 16kHz, 16-bit mono = 320 bytes.
  static const int frameSize = 320;

  @override
  BleAudioCodec get codec => BleAudioCodec.pcm16;

  @override
  String get deviceId => 'phone-mic';

  @override
  String get deviceModel => 'Phone Microphone';

  final List<int> _buffer = [];
  int _frameIndex = 0;

  @override
  List<WalFrame> processBytes(List<int> rawBytes) {
    _buffer.addAll(rawBytes);
    final frames = <WalFrame>[];

    while (_buffer.length >= frameSize) {
      final payload = _buffer.sublist(0, frameSize);
      _buffer.removeRange(0, frameSize);

      frames.add(WalFrame(
        payload: payload,
        syncKey: FrameSyncKey.fromIndex(_frameIndex),
      ));
      // 1-byte index wraps at 256. This mirrors BLE firmware behavior where
      // packet IDs also repeat. markFrameSynced reverse-scans so the most
      // recent frame is always matched first. Safe because _chunk drains
      // frames every ~75s, well within the 256-frame window at 100 fps.
      _frameIndex = (_frameIndex + 1) & 0xFF;
    }

    return frames;
  }

  @override
  List<int> getSocketPayload(List<int> rawBytes) {
    return rawBytes;
  }

  @override
  List<WalFrame> flush() {
    if (_buffer.isEmpty) return [];

    final padded = List<int>.filled(frameSize, 0);
    for (int i = 0; i < _buffer.length; i++) {
      padded[i] = _buffer[i];
    }
    _buffer.clear();

    final frame = WalFrame(
      payload: padded,
      syncKey: FrameSyncKey.fromIndex(_frameIndex),
    );
    _frameIndex = (_frameIndex + 1) & 0xFF;
    return [frame];
  }
}
