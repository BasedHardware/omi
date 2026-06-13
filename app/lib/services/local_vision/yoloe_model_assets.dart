import 'dart:convert';

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
  static const modelDirectory = 'assets/models/yoloe-26n-seg-pf_ncnn_model';
  static const requiredAssetPaths = [
    '$modelDirectory/model.ncnn.param',
    '$modelDirectory/model.ncnn.bin',
    '$modelDirectory/metadata.yaml',
    '$modelDirectory/labels.json',
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

      final labelsText = await rootBundle.loadString('$modelDirectory/labels.json');
      final labelsJson = jsonDecode(labelsText) as Map<String, dynamic>;
      final labels = labelsJson['labels'];
      if (labels is! List || labels.isEmpty) {
        return _invalid('labels.json does not contain a non-empty labels list');
      }

      for (final item in labels) {
        if (item is! Map || item['id'] is! int || item['name'] is! String || (item['name'] as String).trim().isEmpty) {
          return _invalid('labels.json contains an invalid label entry');
        }
      }

      final declaredCount = labelsJson['label_count'];
      if (declaredCount is int && declaredCount != labels.length) {
        return _invalid('labels.json label_count=$declaredCount but labels has ${labels.length} entries');
      }

      final metadataText = await rootBundle.loadString('$modelDirectory/metadata.yaml');
      final inputSize = _parseInputSize(metadataText);
      if (!metadataText.contains('task: segment')) {
        return _invalid('metadata.yaml is not a YOLOE segmentation export');
      }

      return YoloeModelAssetStatus(
        isValid: true,
        modelDirectory: modelDirectory,
        labelCount: labels.length,
        inputSize: inputSize,
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

  static String _parseInputSize(String metadataText) {
    final lines = metadataText.split('\n');
    final imgszIndex = lines.indexWhere((line) => line.trim() == 'imgsz:');
    if (imgszIndex == -1 || imgszIndex + 2 >= lines.length) return 'unknown';

    final width = lines[imgszIndex + 1].replaceFirst('-', '').trim();
    final height = lines[imgszIndex + 2].replaceFirst('-', '').trim();
    if (width.isEmpty || height.isEmpty) return 'unknown';
    return '${width}x$height';
  }
}
