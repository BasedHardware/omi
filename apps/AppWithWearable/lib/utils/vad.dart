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

import 'dart:io';

import 'dart:async';
import 'package:flutter/services.dart';
import 'package:fonnx/models/sileroVad/silero_vad.dart';
import 'package:path_provider/path_provider.dart' as path_provider;
import 'package:path/path.dart' as path;

import 'package:flutter/foundation.dart';

class VadUtil {
  SileroVad? vad;
  dynamic hn;
  dynamic cn;


  init() async {
    final modelPath = await getModelPath('silero_vad.onnx');
    vad = SileroVad.load(modelPath);
  }

  Future<bool> predict(Uint8List bytes) async {
    if (vad == null) return true;
    final result = await vad!.doInference(bytes, previousState:  {
      'hn': hn,
      'cn': cn,
    });
    hn = result['hn'];
    cn = result['cn'];
    debugPrint('Result output: ${result['output'][0]}');
    return result['output'][0] > 0.1; // what's the right threshold?
  }

  Future<String> getModelPath(String modelFilenameWithExtension) async {
    if (kIsWeb) {
      return 'assets/$modelFilenameWithExtension';
    }
    final assetCacheDirectory = await path_provider.getApplicationSupportDirectory();
    final modelPath = path.join(assetCacheDirectory.path, modelFilenameWithExtension);

    File file = File(modelPath);
    bool fileExists = await file.exists();
    final fileLength = fileExists ? await file.length() : 0;

// Do not use path package / path.join for paths.
// After testing on Windows, it appears that asset paths are _always_ Unix style, i.e.
// use /, but path.join uses \ on Windows.
    final assetPath = 'assets/${path.basename(modelFilenameWithExtension)}';
    final assetByteData = await rootBundle.load(assetPath);
    final assetLength = assetByteData.lengthInBytes;
    final fileSameSize = fileLength == assetLength;
    if (!fileExists || !fileSameSize) {
      debugPrint('Copying model to $modelPath. Why? Either the file does not exist (${!fileExists}), '
          'or it does exist but is not the same size as the one in the assets '
          'directory. (${!fileSameSize})');
      debugPrint('About to get byte data for $modelPath');

      List<int> bytes = assetByteData.buffer.asUint8List(
        assetByteData.offsetInBytes,
        assetByteData.lengthInBytes,
      );
      debugPrint('About to copy model to $modelPath');
      try {
        if (!fileExists) {
          await file.create(recursive: true);
        }
        await file.writeAsBytes(bytes, flush: true);
      } catch (e) {
        debugPrint('Error writing bytes to $modelPath: $e');
        rethrow;
      }
      debugPrint('Copied model to $modelPath');
    }

    return modelPath;
  }
}
