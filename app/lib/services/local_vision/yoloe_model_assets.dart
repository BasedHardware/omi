import 'package:flutter/services.dart';

class YoloeModelAssetStatus {
  const YoloeModelAssetStatus({
    required this.isValid,
    required this.modelDirectory,
    required this.labelCount,
    required this.inputSize,
    required this.requiredAssets,
    this.error,
  });

  const YoloeModelAssetStatus.notChecked()
      : isValid = false,
        modelDirectory = YoloeModelAssets.modelDirectory,
        labelCount = 0,
        inputSize = 'unknown',
        requiredAssets = YoloeModelAssets.requiredAssetPaths,
        error = null;

  final bool isValid;
  final String modelDirectory;
  final int labelCount;
  final String inputSize;
  final List<String> requiredAssets;
  final String? error;

  String get displayName => isValid ? 'Ready' : 'Unavailable';
}

class YoloeModelAssets {
  static const modelDirectory = 'assets/models/yoloe-26n-seg-pf';
  static const modelPath = '$modelDirectory/yoloe-26n-seg-pf.onnx2tf-fixed_float32.tflite';
  static const labelsPath = '$modelDirectory/labels.json';
  static const physicalObjectTagsPath = 'assets/models/ram_physical_object_tag_list.txt';
  static const requiredAssetPaths = [
    modelPath,
    labelsPath,
    physicalObjectTagsPath,
  ];

  const YoloeModelAssets._();

  static Future<YoloeModelAssetStatus> validate() async {
    try {
      for (final path in requiredAssetPaths) {
        final data = await rootBundle.load(path);
        if (data.lengthInBytes == 0) {
          return _invalid('Model asset is empty: $path');
        }
      }

      return const YoloeModelAssetStatus(
        isValid: true,
        modelDirectory: modelDirectory,
        labelCount: 4585,
        inputSize: '640x640',
        requiredAssets: requiredAssetPaths,
      );
    } catch (e) {
      return _invalid('Failed to validate YOLOE model assets: $e');
    }
  }

  static YoloeModelAssetStatus _invalid(String error) {
    return YoloeModelAssetStatus(
      isValid: false,
      modelDirectory: modelDirectory,
      labelCount: 0,
      inputSize: 'unknown',
      requiredAssets: requiredAssetPaths,
      error: error,
    );
  }
}
