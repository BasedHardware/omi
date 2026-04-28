import 'package:omi/backend/preferences.dart';

enum AmbientCaptureMode { off, normal, aggressive, workHours, meeting, private }

enum AmbientCommunicationMode { off, detectOnly, detectAndAttemptMic, detectAndCaptionFallback }

class AmbientCapturePolicy {
  final int version;
  final String pluginId;
  final String scope;
  final String userId;
  final String deviceId;
  final int sequence;
  final DateTime issuedAt;
  final DateTime validUntil;
  final AmbientCaptureMode captureMode;
  final String sensitivity;
  final int silenceDetectionSeconds;
  final double rmsSilenceDbfsThreshold;
  final double zeroFrameThreshold;
  final bool allowForegroundMic;
  final bool allowAccessibilityMode;
  final bool allowLocalSttFallback;
  final bool allowCaptionFallback;
  final bool allowAudioUpload;
  final bool allowTranscriptUpload;
  final String rawAudioRetention;
  final AmbientCommunicationMode communicationMode;
  final List<String> highRiskApps;
  final String notificationAggressiveness;
  final String auditLevel;

  const AmbientCapturePolicy({
    required this.version,
    required this.pluginId,
    required this.scope,
    required this.userId,
    required this.deviceId,
    required this.sequence,
    required this.issuedAt,
    required this.validUntil,
    required this.captureMode,
    required this.sensitivity,
    required this.silenceDetectionSeconds,
    required this.rmsSilenceDbfsThreshold,
    required this.zeroFrameThreshold,
    required this.allowForegroundMic,
    required this.allowAccessibilityMode,
    required this.allowLocalSttFallback,
    required this.allowCaptionFallback,
    required this.allowAudioUpload,
    required this.allowTranscriptUpload,
    required this.rawAudioRetention,
    required this.communicationMode,
    required this.highRiskApps,
    required this.notificationAggressiveness,
    required this.auditLevel,
  });

  factory AmbientCapturePolicy.fromJson(Map<String, dynamic> json) {
    return AmbientCapturePolicy(
      version: json['version'] as int? ?? 1,
      pluginId: json['plugin_id']?.toString() ?? '',
      scope: json['scope']?.toString() ?? '',
      userId: json['user_id']?.toString() ?? '',
      deviceId: json['device_id']?.toString() ?? '',
      sequence: json['sequence'] as int? ?? 0,
      issuedAt: DateTime.parse(json['issued_at']?.toString() ?? DateTime.fromMillisecondsSinceEpoch(0).toIso8601String()),
      validUntil: DateTime.parse(json['valid_until']?.toString() ?? DateTime.fromMillisecondsSinceEpoch(0).toIso8601String()),
      captureMode: _captureMode(json['capture_mode']?.toString()),
      sensitivity: json['sensitivity']?.toString() ?? 'medium',
      silenceDetectionSeconds: json['silence_detection_seconds'] as int? ?? 12,
      rmsSilenceDbfsThreshold: (json['rms_silence_dbfs_threshold'] as num?)?.toDouble() ?? -75,
      zeroFrameThreshold: (json['zero_frame_threshold'] as num?)?.toDouble() ?? 0.98,
      allowForegroundMic: json['allow_foreground_mic'] as bool? ?? false,
      allowAccessibilityMode: json['allow_accessibility_mode'] as bool? ?? false,
      allowLocalSttFallback: json['allow_local_stt_fallback'] as bool? ?? false,
      allowCaptionFallback: json['allow_caption_fallback'] as bool? ?? false,
      allowAudioUpload: json['allow_audio_upload'] as bool? ?? false,
      allowTranscriptUpload: json['allow_transcript_upload'] as bool? ?? false,
      rawAudioRetention: json['raw_audio_retention']?.toString() ?? 'none',
      communicationMode: _communicationMode(json['communication_mode']?.toString()),
      highRiskApps: (json['high_risk_apps'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
      notificationAggressiveness: json['notification_aggressiveness']?.toString() ?? 'quiet',
      auditLevel: json['audit_level']?.toString() ?? 'basic',
    );
  }

  static AmbientCaptureMode _captureMode(String? value) {
    switch (value) {
      case 'normal':
        return AmbientCaptureMode.normal;
      case 'aggressive':
        return AmbientCaptureMode.aggressive;
      case 'work_hours':
        return AmbientCaptureMode.workHours;
      case 'meeting':
        return AmbientCaptureMode.meeting;
      case 'private':
        return AmbientCaptureMode.private;
      default:
        return AmbientCaptureMode.off;
    }
  }

  static AmbientCommunicationMode _communicationMode(String? value) {
    switch (value) {
      case 'detect_only':
        return AmbientCommunicationMode.detectOnly;
      case 'detect_and_attempt_mic':
        return AmbientCommunicationMode.detectAndAttemptMic;
      case 'detect_and_caption_fallback':
        return AmbientCommunicationMode.detectAndCaptionFallback;
      default:
        return AmbientCommunicationMode.off;
    }
  }
}

class AmbientPolicyDecision {
  final bool accepted;
  final String reason;

  const AmbientPolicyDecision.accepted() : accepted = true, reason = 'ok';
  const AmbientPolicyDecision.rejected(this.reason) : accepted = false;
}

class AmbientCapturePolicyValidator {
  AmbientPolicyDecision validate({
    required AmbientCapturePolicy policy,
    required String expectedPluginId,
    required String expectedUserId,
    required String expectedDeviceId,
    required int lastSequence,
    required bool accessibilityEnabled,
    bool privateModeActive = false,
    DateTime? now,
  }) {
    final prefs = SharedPreferencesUtil();
    final current = now ?? DateTime.now().toUtc();
    if (!prefs.advancedAmbientCaptureEnabled) return const AmbientPolicyDecision.rejected('master_disabled');
    if (!prefs.ambientCapturePluginControlEnabled) return const AmbientPolicyDecision.rejected('plugin_control_disabled');
    if (privateModeActive) return const AmbientPolicyDecision.rejected('private_mode_active');
    if (policy.scope != 'ambient_capture_controller') return const AmbientPolicyDecision.rejected('missing_scope');
    if (policy.pluginId != expectedPluginId) return const AmbientPolicyDecision.rejected('wrong_plugin');
    if (policy.userId != expectedUserId) return const AmbientPolicyDecision.rejected('wrong_user');
    if (policy.deviceId != expectedDeviceId) return const AmbientPolicyDecision.rejected('wrong_device');
    if (policy.sequence <= lastSequence) return const AmbientPolicyDecision.rejected('replayed_sequence');
    if (policy.issuedAt.toUtc().isAfter(current.add(const Duration(minutes: 5)))) {
      return const AmbientPolicyDecision.rejected('issued_in_future');
    }
    if (!policy.validUntil.toUtc().isAfter(current)) return const AmbientPolicyDecision.rejected('expired');
    if (policy.allowAccessibilityMode && (!prefs.ambientCaptureAccessibilityModeEnabled || !accessibilityEnabled)) {
      return const AmbientPolicyDecision.rejected('accessibility_not_granted');
    }
    if (policy.allowAudioUpload && !prefs.ambientCaptureRawAudioUploadEnabled) {
      return const AmbientPolicyDecision.rejected('raw_audio_upload_disabled');
    }
    return const AmbientPolicyDecision.accepted();
  }
}
