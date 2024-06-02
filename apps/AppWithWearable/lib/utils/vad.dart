// import 'dart:io';
// import 'dart:typed_data';
//
// import 'package:flutter/material.dart';
// import 'package:flutter/services.dart';
// import 'package:flutter_silero_vad/flutter_silero_vad.dart';
// import 'package:path_provider/path_provider.dart';

// final vad = FlutterSileroVad();
//     await onnxModelToLocal();
//     await vad.initialize(
//       modelPath: await modelPath,
//       sampleRate: 8000,
//       frameSize: 40,
//       threshold: 0.7,
//       minSilenceDurationMs: 100,
//       speechPadMs: 0,
//     );

// Future<String> get modelPath async => '${(await getApplicationSupportDirectory()).path}/silero_vad.onnx';
//
// predict(FlutterSileroVad vad, List<int> audioBytes) async {
//   final bytes = Uint8List.fromList(audioBytes);
//   final bytes2 = Int16List.view(bytes.buffer);
//   final bytes3 = bytes2.map((e) => e / 32768).toList();
//   final isActivated = await vad.predict(Float32List.fromList(bytes3));
//   debugPrint('VAD: $isActivated');
// }
//
// Future<void> onnxModelToLocal() async {
//   final data = await rootBundle.load('assets/silero_vad.onnx');
//   final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
//   File(await modelPath).writeAsBytesSync(bytes);
// }
