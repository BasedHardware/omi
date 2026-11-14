import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/services/sockets/apple_speech_readiness.dart';

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
  @visibleForTesting
  FreemiumTranscriptionService.testing({this.iosOverride, this.appleReadinessReader});
  bool? iosOverride;
  Future<AppleSpeechReadiness> Function(String)? appleReadinessReader;
  AppleSpeechReadiness? appleReadiness;

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
  static String effectiveLanguage({String? language}) {
    final preferences = SharedPreferencesUtil();
    final config = preferences.customSttConfig;
    final selected = language ??
        (config.isEnabled && config.provider == SttProvider.onDeviceWhisper
            ? (config.language ?? 'en')
            : preferences.userPrimaryLanguage);
    return selected.isEmpty ? 'multi' : selected;
  }

  Future<FreemiumReadiness> checkReadiness({String? language}) async {
    if (iosOverride ?? Platform.isIOS) {
      appleReadiness =
          await (appleReadinessReader ?? OnDeviceAppleProvider.readiness)(effectiveLanguage(language: language));
      _readiness = appleReadiness!.ready ? FreemiumReadiness.ready : FreemiumReadiness.requiresSetup;
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
      Logger.debug('[Freemium] Error checking model readiness: $e');
    }

    _readiness = FreemiumReadiness.requiresSetup;
    notifyListeners();
    return _readiness;
  }

  void reportLocalFailure(String status) {
    _readiness = FreemiumReadiness.requiresSetup;
    if (Platform.isIOS) appleReadiness = AppleSpeechReadiness('sfspeech', status);
    notifyListeners();
  }

  /// Smaller models are faster and need less memory, so they win when nothing was chosen.
  static const modelPriority = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2'];

  /// Picks the model to run out of the ones actually on disk.
  ///
  /// The model selected in settings wins; [modelPriority] is only the fallback. Without this, a
  /// user who downloads `base` while an older `tiny` is still present silently runs `tiny`, so the
  /// model picker on the transcription settings page appears to do nothing.
  static String? chooseModelPath(
    List<String> binPaths, {
    String? preferredModel,
    String? preferredPath,
  }) {
    if (binPaths.isEmpty) return null;

    String basename(String path) => path.replaceAll('\\', '/').split('/').last.toLowerCase();

    if (preferredPath != null && preferredPath.isNotEmpty) {
      final wanted = basename(preferredPath);
      for (final path in binPaths) {
        if (basename(path) == wanted) return path;
      }
    }

    final order = <String>[
      if (preferredModel != null && preferredModel.isNotEmpty) preferredModel,
      ...modelPriority,
    ];
    for (final name in order) {
      final wanted = 'ggml-${name.toLowerCase()}.bin';
      for (final path in binPaths) {
        if (basename(path) == wanted) return path;
      }
    }

    return binPaths.first;
  }

  /// Find the Whisper model to run in the models directory.
  Future<String?> _findDownloadedModelPath() async {
    try {
      final appDir = await getApplicationSupportDirectory();
      final modelDir = Directory('${appDir.path}/models');

      if (!await modelDir.exists()) {
        return null;
      }

      final files = await modelDir.list().toList();
      final binFiles = files.whereType<File>().where((f) => f.path.endsWith('.bin')).toList();

      // Only this provider's own saved config is a deliberate choice of whisper model.
      final config = SharedPreferencesUtil().customSttConfig;
      final chose = config.isEnabled && config.provider == SttProvider.onDeviceWhisper;

      final path = chooseModelPath(
        binFiles.map((file) => file.path).toList(),
        preferredModel: chose ? config.model : null,
        preferredPath: chose ? config.url : null,
      );
      if (path != null) Logger.debug('[Freemium] Using model: $path');
      return path;
    } catch (e) {
      Logger.debug('[Freemium] Error finding model: $e');
    }
    return null;
  }

  /// Get the cached model path (call checkReadiness first)
  String? get cachedModelPath => _cachedModelPath;

  /// Create a CustomSttConfig for on-device STT (iOS uses Apple, others use Whisper)
  CustomSttConfig createOnDeviceSttConfig({String? language, String? modelPath}) {
    final userLang = SharedPreferencesUtil().userPrimaryLanguage;
    final effectiveLanguage = language ?? (userLang.isNotEmpty ? userLang : 'multi');

    if (Platform.isIOS) {
      // Use Apple's native speech recognition
      return CustomSttConfig(
        provider: SttProvider.onDeviceWhisper, // Uses OnDeviceAppleProvider on iOS
        language: effectiveLanguage,
        sendRawAudioToOmi: false,
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
      sendRawAudioToOmi: false,
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
