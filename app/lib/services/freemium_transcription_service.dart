import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

/// Enum representing the current freemium transcription state
enum FreemiumTranscriptionState {
  /// Using premium (Omi) STT
  premium,

  /// Using free (on-device) STT
  free,
}

/// Enum for freemium readiness status
enum FreemiumReadiness {
  /// On-device STT is ready to use
  ready,

  /// On-device STT requires setup (model download, etc.)
  requiresSetup,

  /// Platform not supported for on-device STT
  notSupported,
}

/// Service to manage freemium transcription state
/// Handles checking on-device readiness and config generation
class FreemiumTranscriptionService extends ChangeNotifier {
  static final FreemiumTranscriptionService _instance = FreemiumTranscriptionService._internal();
  factory FreemiumTranscriptionService() => _instance;
  FreemiumTranscriptionService._internal();

  FreemiumTranscriptionState _state = FreemiumTranscriptionState.premium;
  FreemiumReadiness _readiness = FreemiumReadiness.requiresSetup;
  bool _paywallShownThisSession = false;
  String? _cachedModelPath;

  /// Callback when user switches to free (optional)
  VoidCallback? onAutoSwitch;

  FreemiumTranscriptionState get state => _state;
  FreemiumReadiness get readiness => _readiness;
  bool get dialogShownThisSession => _paywallShownThisSession;

  /// Mark paywall as shown for this session
  void markDialogShown() {
    _paywallShownThisSession = true;
  }

  /// Reset paywall shown flag (e.g., for new recording session)
  void resetDialogShownFlag() {
    _paywallShownThisSession = false;
  }

  /// Check if freemium (on-device) STT is ready to use
  Future<FreemiumReadiness> checkReadiness() async {
    // iOS: Native Apple Speech Recognition is always available
    if (Platform.isIOS) {
      _readiness = FreemiumReadiness.ready;
      notifyListeners();
      return _readiness;
    }

    // macOS: Also has native speech recognition
    if (Platform.isMacOS) {
      _readiness = FreemiumReadiness.ready;
      notifyListeners();
      return _readiness;
    }

    // Android/Other: Check if any Whisper model is downloaded
    try {
      final modelPath = await _findDownloadedModelPath();
      if (modelPath != null) {
        _cachedModelPath = modelPath;
        _readiness = FreemiumReadiness.ready;
        notifyListeners();
        return _readiness;
      }
    } catch (e) {
      debugPrint('[Freemium] Error checking model readiness: $e');
    }

    _readiness = FreemiumReadiness.requiresSetup;
    notifyListeners();
    return _readiness;
  }

  /// Find any downloaded Whisper model in the models directory
  /// Returns the path to the first found model, preferring smaller models
  Future<String?> _findDownloadedModelPath() async {
    try {
      final appDir = await getApplicationSupportDirectory();
      final modelDir = Directory('${appDir.path}/models');

      if (!await modelDir.exists()) {
        return null;
      }

      // Prefer smaller models (faster, less resource usage)
      const modelPriority = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2'];

      final files = await modelDir.list().toList();
      final binFiles = files.whereType<File>().where((f) => f.path.endsWith('.bin')).toList();

      if (binFiles.isEmpty) {
        return null;
      }

      // Try to find by priority
      for (final modelName in modelPriority) {
        for (final file in binFiles) {
          if (file.path.contains('ggml-$modelName.bin') && await file.exists()) {
            debugPrint('[Freemium] Found model: ${file.path}');
            return file.path;
          }
        }
      }

      // Fallback to any .bin file
      debugPrint('[Freemium] Using fallback model: ${binFiles.first.path}');
      return binFiles.first.path;
    } catch (e) {
      debugPrint('[Freemium] Error finding model: $e');
    }
    return null;
  }

  /// Get the cached model path (call checkReadiness first)
  String? get cachedModelPath => _cachedModelPath;

  /// Create a CustomSttConfig for on-device STT (iOS uses Apple, others use Whisper)
  CustomSttConfig createOnDeviceSttConfig({String? language, String? modelPath}) {
    final userLang = SharedPreferencesUtil().userPrimaryLanguage;
    final effectiveLanguage = language ?? (userLang.isNotEmpty ? userLang : 'multi');

    if (Platform.isIOS || Platform.isMacOS) {
      // Use Apple's native speech recognition
      return CustomSttConfig(
        provider: SttProvider.onDeviceWhisper, // Uses OnDeviceAppleProvider on iOS
        language: effectiveLanguage,
      );
    }

    // For Android/other platforms, use the provided or cached model path
    final effectiveModelPath = modelPath ?? _cachedModelPath;

    // Extract model name from path (e.g., "ggml-tiny.bin" -> "tiny")
    String? modelName;
    if (effectiveModelPath != null) {
      final fileName = effectiveModelPath.split('/').last;
      final match = RegExp(r'ggml-(\w+)\.bin').firstMatch(fileName);
      if (match != null) {
        modelName = match.group(1);
      }
    }

    return CustomSttConfig(
      provider: SttProvider.onDeviceWhisper,
      language: effectiveLanguage,
      model: modelName ?? 'tiny',
      url: effectiveModelPath,
    );
  }

  /// Get the CustomSttConfig to use for freemium mode
  /// Returns null if not ready
  CustomSttConfig? getFreemiumConfig() {
    if (_readiness != FreemiumReadiness.ready) {
      return null;
    }
    return createOnDeviceSttConfig(modelPath: _cachedModelPath);
  }

  /// Switch to free (on-device) STT
  void switchToFree() {
    _state = FreemiumTranscriptionState.free;
    notifyListeners();
    onAutoSwitch?.call();
  }

  /// Switch back to premium STT
  void switchToPremium() {
    _state = FreemiumTranscriptionState.premium;
    notifyListeners();
  }

  /// Check if currently using free (on-device) STT
  bool get isUsingFreeStt => _state == FreemiumTranscriptionState.free;

  /// Check if currently using premium (Omi) STT
  bool get isUsingPremiumStt => _state == FreemiumTranscriptionState.premium;

  /// Reset state
  void reset() {
    _state = FreemiumTranscriptionState.premium;
    _readiness = FreemiumReadiness.requiresSetup;
    _paywallShownThisSession = false;
    notifyListeners();
  }
}
