import 'package:nooto_v2/audio/codec.dart';
import 'package:nooto_v2/services/audio_sources/audio_source.dart';

/// Audio source for the phone's built-in microphone.
///
/// Phone mic records PCM16 audio at 16 kHz mono. Raw bytes arrive in
/// variable-sized chunks from the platform microphone API. This source
/// buffers incoming bytes and splits them into fixed 320-byte frames
/// (10 ms at 16 kHz, 16-bit mono = 160 samples × 2 bytes).
///
/// **Audio parity:** these constants must stay identical to the legacy
/// `app/lib/services/audio_sources/phone_mic_source.dart` and to
/// desktop-v2's Tauri capture plugin.
class PhoneMicSource implements AudioSource {
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
      _frameIndex = (_frameIndex + 1) & 0xFF;
    }

    return frames;
  }

  @override
  List<int> getSocketPayload(List<int> rawBytes) => rawBytes;

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
