import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_silero_vad/flutter_silero_vad.dart';
import 'package:path_provider/path_provider.dart';

class VadUtil {
  final vad = FlutterSileroVad();
  final int sampleRate = 8000;

  Future<void> init() async {
    await onnxModelToLocal();
    await vad.initialize(
      modelPath: await modelPath,
      sampleRate: sampleRate,
      frameSize: 160,
      // 20ms at 8kHz
      threshold: 0.8,
      minSilenceDurationMs: 100,
      speechPadMs: 0,
    );
    print('VAD model initialized successfully');
  }

  Future<String> get modelPath async => '${(await getApplicationSupportDirectory()).path}/silero_vad.onnx';

  Future<void> onnxModelToLocal() async {
    File modelFile = File(await modelPath);
    if (await modelFile.exists()) {
      print('Model file size: ${await modelFile.length()} bytes');
    } else {
      print('Model file does not exist. Please ensure it\'s properly copied to the device.');
    }
    // Implement the logic to copy the model file if it doesn't exist
  }

  Float32List normalizeAndCenterAudio(Float32List audio) {
    double minVal = audio.reduce(min);
    double maxVal = audio.reduce(max);
    double range = maxVal - minVal;
    return Float32List.fromList(audio.map((sample) => (2 * (sample - minVal) / range) - 1).toList());
  }

  bool simpleVAD(Float32List frame, double threshold) {
    double energy = frame.map((s) => s * s).reduce((a, b) => a + b) / frame.length;
    return energy > threshold;
  }

  bool isMainlySilence(Float32List audio, double threshold) {
    double energy = audio.map((sample) => sample * sample).reduce((a, b) => a + b) / audio.length;
    return energy < threshold;
  }

  bool isSignificantEnergyChange(double energyDiff, double threshold) {
    return energyDiff.abs() > threshold;
  }

  bool containsSignificantVoice(List<bool> vadResults, int minContiguousFrames) {
    int contiguousCount = 0;
    for (bool result in vadResults) {
      if (result) {
        contiguousCount++;
        if (contiguousCount >= minContiguousFrames) return true;
      } else {
        contiguousCount = 0;
      }
    }
    return false;
  }

  Future<bool> containsVoice(File file) async {
    final bytes = await file.readAsBytes();
    final int16List = Int16List.view(bytes.buffer);
    var float32List = Float32List.fromList(int16List.map((e) => e / 32768).toList());

    print('Original sample range: ${float32List.reduce(min)} to ${float32List.reduce(max)}');

    float32List = normalizeAndCenterAudio(float32List);
    print('Normalized sample range: ${float32List.reduce(min)} to ${float32List.reduce(max)}');

    if (isMainlySilence(float32List, 0.0001)) {
      print('Audio is mainly silence');
      return false;
    }

    final frameSize = 160;
    int sileroVADCount = 0;
    int simpleVADCount = 0;
    double lastEnergy = 0;
    List<bool> vadResults = [];
    List<double> voiceRatios = [];

    for (var i = 0; i < float32List.length; i += frameSize) {
      final end = min(i + frameSize, float32List.length);
      final frame = float32List.sublist(i, end);

      // Silero VAD
      bool? sileroVADResult = await vad.predict(frame);

      // Simple VAD
      bool simpleVADResult = simpleVAD(frame, 0.1); // Increased threshold

      // Energy difference
      double energy = frame.map((s) => s * s).reduce((a, b) => a + b) / frame.length;
      double energyDiff = energy - lastEnergy;
      bool significantEnergyChange = isSignificantEnergyChange(energyDiff, 0.05);

      // Combined voice detection
      bool isVoice = sileroVADResult == true && significantEnergyChange;
      vadResults.add(isVoice);

      // Logging
      if (i % (frameSize * 100) == 0) {
        // Log every 100th frame to avoid excessive output
        print('Frame ${i ~/ frameSize}: '
            'Silero VAD = $sileroVADResult, '
            'Simple VAD = $simpleVADResult, '
            'Energy Diff = $energyDiff, '
            'Significant Energy Change = $significantEnergyChange, '
            'Is Voice = $isVoice');
      }

      // Counting
      if (sileroVADResult == true) sileroVADCount++;
      if (simpleVADResult) simpleVADCount++;

      lastEnergy = energy;

      // Calculate voice ratios for 1-second segments
      if (vadResults.length % 50 == 0) {
        int start = vadResults.length - 50;
        double ratio = vadResults.sublist(start).where((r) => r).length / 50;
        voiceRatios.add(ratio);
      }
    }

    print('Frames with voice (Silero VAD): $sileroVADCount');
    print('Frames with voice (Simple VAD): $simpleVADCount');

    bool hasSignificantVoice = containsSignificantVoice(vadResults, 30);
    print('Contains significant voice: $hasSignificantVoice');

    bool containsVoiceSegments = voiceRatios.any((ratio) => ratio > 0.5);
    print('Contains voice segments: $containsVoiceSegments');

    // Final decision combining multiple methods
    return hasSignificantVoice || containsVoiceSegments;
  }
}
