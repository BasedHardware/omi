import 'dart:async';
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

  /// Auto-switching countdown in progress
  switching,
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

/// Service to manage freemium transcription switching
/// Handles auto-switch countdown when premium minutes are low
class FreemiumTranscriptionService extends ChangeNotifier {
  static final FreemiumTranscriptionService _instance = FreemiumTranscriptionService._internal();
  factory FreemiumTranscriptionService() => _instance;
  FreemiumTranscriptionService._internal();

  FreemiumTranscriptionState _state = FreemiumTranscriptionState.premium;
  FreemiumReadiness _readiness = FreemiumReadiness.requiresSetup;
  Timer? _countdownTimer;
  int _countdownSeconds = 10;
  bool _dialogShownThisSession = false;
  String? _cachedModelPath;

  /// Callback when auto-switch should happen
  VoidCallback? onAutoSwitch;

  FreemiumTranscriptionState get state => _state;
  FreemiumReadiness get readiness => _readiness;
  int get countdownSeconds => _countdownSeconds;
  bool get isCountdownActive => _countdownTimer?.isActive ?? false;
  bool get dialogShownThisSession => _dialogShownThisSession;

  /// Mark dialog as shown for this session
  void markDialogShown() {
    _dialogShownThisSession = true;
  }

  /// Reset dialog shown flag (e.g., for new recording session)
  void resetDialogShownFlag() {
    _dialogShownThisSession = false;
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

  /// Start the auto-switch countdown
  /// Returns true if countdown started, false if not ready
  bool startAutoSwitchCountdown({int seconds = 10}) {
    if (_readiness != FreemiumReadiness.ready) {
      return false;
    }

    cancelCountdown();
    _countdownSeconds = seconds;
    _state = FreemiumTranscriptionState.switching;
    notifyListeners();

    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      _countdownSeconds--;
      notifyListeners();

      if (_countdownSeconds <= 0) {
        timer.cancel();
        _performAutoSwitch();
      }
    });

    return true;
  }

  /// Cancel the countdown and stay on premium
  void cancelCountdown() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
    _countdownSeconds = 10;
    if (_state == FreemiumTranscriptionState.switching) {
      _state = FreemiumTranscriptionState.premium;
      notifyListeners();
    }
  }

  /// Perform the auto-switch to free STT
  void _performAutoSwitch() {
    _state = FreemiumTranscriptionState.free;
    notifyListeners();
    onAutoSwitch?.call();
  }

  /// Manually switch to free STT immediately
  void switchToFreeNow() {
    cancelCountdown();
    _state = FreemiumTranscriptionState.free;
    notifyListeners();
    onAutoSwitch?.call();
  }

  /// Switch back to premium STT
  void switchToPremium() {
    cancelCountdown();
    _state = FreemiumTranscriptionState.premium;
    notifyListeners();
  }

  /// Check if currently using free (on-device) STT
  bool get isUsingFreeStt => _state == FreemiumTranscriptionState.free;

  /// Check if currently using premium (Omi) STT
  bool get isUsingPremiumStt => _state == FreemiumTranscriptionState.premium;

  /// Reset state (e.g., when user logs out or recording stops)
  void reset() {
    cancelCountdown();
    _state = FreemiumTranscriptionState.premium;
    _readiness = FreemiumReadiness.requiresSetup;
    _dialogShownThisSession = false;
    notifyListeners();
  }

  @override
  void dispose() {
    cancelCountdown();
    super.dispose();
  }
}
