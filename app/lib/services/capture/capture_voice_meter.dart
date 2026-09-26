import 'dart:math' as math;
import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/logger.dart';

/// Decodes one Opus packet to 16 kHz mono PCM16 samples.
typedef OpusPacketDecoder = Int16List Function(Uint8List packet);

/// Loudness history for the recording Live Activity. Presentation only: it
/// observes captured audio and never gates, buffers or alters capture.
///
/// Loudness is the same RMS measure the voice introduction uses for "Audio
/// detected" (GuidedVoiceController): RMS / 1800, voiced above 0.04. Audio is
/// folded into fixed time bins, and voice stays active briefly after the last
/// voiced bin so pauses between words do not flicker.
class CaptureVoiceMeter {
  CaptureVoiceMeter({required DateTime Function() now, OpusPacketDecoder Function()? opusDecoder, this.onDispose})
      : _now = now,
        _opusDecoderFactory = opusDecoder;

  /// The meter of the running app (iOS), for presentation that shows the live audio level (the
  /// Live page's level strip). Null where no meter is composed.
  static CaptureVoiceMeter? active;

  static const binMilliseconds = 125;
  static const history = 80;
  static const _hangoverBins = 12;
  static const _fullScaleRms = 1800.0;
  static const _voiceLevel = 0.04;

  final DateTime Function() _now;
  final OpusPacketDecoder Function()? _opusDecoderFactory;
  final void Function()? onDispose;
  OpusPacketDecoder? _opus;
  bool _opusUnavailable = false;

  final _levels = List<int>.filled(history, 0);
  int? _lastBin;
  int? _lastAudioBin;
  int? _lastVoicedBin;
  double _binPeak = 0;

  /// Whether audio this meter can measure has arrived recently.
  bool get hasSignal => _lastAudioBin != null && _bin() - _lastAudioBin! <= _hangoverBins;

  bool get voiceActive => _lastVoicedBin != null && _bin() - _lastVoicedBin! <= _hangoverBins;

  /// The newest completed bin; bins are absolute so a presentation can keep
  /// identity as the strip scrolls. The bin still filling is not shown.
  int get latestBin => _bin() - 1;

  /// Display heights 0–100 for the [history] bins ending at [latestBin], oldest first.
  List<int> levels() {
    _advance(_bin());
    final end = latestBin;
    return [for (var i = end - history + 1; i <= end; i++) _levelAt(i)];
  }

  void add(List<int> audio, BleAudioCodec codec) {
    final samples = _decode(audio, codec);
    if (samples == null || samples.isEmpty) return;
    var sum = 0.0;
    for (final sample in samples) {
      sum += sample * sample;
    }
    final level = (math.sqrt(sum / samples.length) / _fullScaleRms).clamp(0.0, 1.0);
    final bin = _bin();
    _advance(bin);
    _lastAudioBin = bin;
    _binPeak = math.max(_binPeak, level);
    _levels[bin % history] = _display(_binPeak);
    if (_binPeak > _voiceLevel) _lastVoicedBin = bin;
  }

  void reset() {
    _levels.fillRange(0, history, 0);
    _lastBin = null;
    _lastAudioBin = null;
    _lastVoicedBin = null;
    _binPeak = 0;
  }

  void dispose() {
    reset();
    _opus = null;
    onDispose?.call();
  }

  int _bin() => _now().millisecondsSinceEpoch ~/ binMilliseconds;

  /// Bar height 0–100 on a loudness (dB) curve: RMS levels span decades, and
  /// quiet pendant speech would otherwise draw near-flat bars. 0.01 (-40 dB)
  /// and below is silence; 0.5 (-6 dB) and above fills the bar.
  static int _display(double level) {
    if (level <= 0) return 0;
    final db = 20 * math.log(level) / math.ln10;
    return ((db + 40) / 34 * 100).round().clamp(0, 100);
  }

  int _levelAt(int bin) {
    if (_lastBin == null || bin > _lastBin! || _lastBin! - bin >= history) return 0;
    return _levels[bin % history];
  }

  /// Closes the finished bin into the noise estimate and clears skipped bins.
  void _advance(int bin) {
    final last = _lastBin;
    if (last == bin) return;
    if (last != null) {
      for (var i = last + 1; i <= bin && i - last <= history; i++) {
        _levels[i % history] = 0;
      }
    }
    _lastBin = bin;
    _binPeak = 0;
  }

  List<int>? _decode(List<int> audio, BleAudioCodec codec) {
    switch (codec) {
      case BleAudioCodec.pcm16:
        // Little-endian PCM16; decoded by hand because views may be unaligned.
        final samples = Int16List(audio.length ~/ 2);
        for (var i = 0; i < samples.length; i++) {
          samples[i] = audio[2 * i] | (audio[2 * i + 1] << 8);
        }
        return samples;
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        if (_opusUnavailable || _opusDecoderFactory == null) return null;
        try {
          _opus ??= _opusDecoderFactory!();
          return _opus!(audio is Uint8List ? audio : Uint8List.fromList(audio));
        } catch (error) {
          // A presentation meter must never disturb capture; stop decoding.
          Logger.warning('Live Activity voice meter: Opus decoding unavailable: $error');
          _opusUnavailable = true;
          return null;
        }
      default:
        return null;
    }
  }
}
