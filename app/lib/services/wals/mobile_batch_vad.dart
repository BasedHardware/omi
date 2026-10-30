import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:onnxruntime_v2/onnxruntime_v2.dart';
import 'package:opus_dart/opus_dart.dart';

/// VAD sees a decoded COPY; the archive always receives original Opus bytes.
/// One native inference worker, 512 samples at 16kHz. Unknown/error is speech
/// for scheduling, never a reason to discard audio or delay it indefinitely.
abstract interface class MobileBatchVad {
  Future<double> probability(List<int> opus);
  Future<void> close();
}

class SileroMobileBatchVad implements MobileBatchVad {
  SileroMobileBatchVad._(this._session, this._options);

  static Future<SileroMobileBatchVad> load() async {
    final model = await rootBundle.load('assets/models/silero_vad.onnx');
    final options = OrtSessionOptions()
      ..setIntraOpNumThreads(1)
      ..setInterOpNumThreads(1);
    try {
      return SileroMobileBatchVad._(OrtSession.fromBuffer(model.buffer.asUint8List(), options), options);
    } catch (_) {
      options.release();
      rethrow;
    }
  }

  final OrtSession _session;
  final OrtSessionOptions _options;
  final SimpleOpusDecoder _decoder = SimpleOpusDecoder(sampleRate: 16000, channels: 1);
  final List<double> _samples = [];
  Float32List _state = Float32List(256);
  Float32List _context = Float32List(64);

  @override
  Future<double> probability(List<int> opus) async {
    final pcm = _decoder.decode(input: Uint8List.fromList(opus));
    _samples.addAll(pcm.map((value) => value / 32768.0));
    double result = 0;
    while (_samples.length >= 512) {
      final window = Float32List(576)
        ..setRange(0, 64, _context)
        ..setRange(64, 576, _samples.take(512));
      _samples.removeRange(0, 512);
      _context = Float32List.fromList(window.sublist(512));
      final input = OrtValueTensor.createTensorWithDataList(window, [1, 576]);
      final state = OrtValueTensor.createTensorWithDataList(_state, [2, 1, 128]);
      final rate = OrtValueTensor.createTensorWithDataList(Int64List.fromList([16000]), []);
      final options = OrtRunOptions();
      List<OrtValue?>? outputs;
      try {
        outputs = await _session.runAsync(options, {'input': input, 'state': state, 'sr': rate});
        if (outputs == null || outputs.length < 2) throw StateError('Missing Silero outputs');
        final probability = (outputs[0]!.value as List)[0][0] as double;
        if (!probability.isFinite) throw StateError('Invalid Silero probability');
        if (probability > result) result = probability;
        _state = Float32List.fromList((outputs[1]!.value as List)
            .expand((plane) => (plane as List).expand((row) => List<double>.from(row as List)))
            .toList());
      } finally {
        for (final output in outputs ?? <OrtValue?>[]) {
          output?.release();
        }
        input.release();
        state.release();
        rate.release();
        options.release();
      }
    }
    return result;
  }

  @override
  Future<void> close() async {
    _decoder.destroy();
    await _session.release();
    _options.release();
  }
}
