import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/ambient_capture/ambient_capture_health.dart';
import 'package:omi/services/ambient_capture/ambient_capture_policy.dart';

void main() {
  late AmbientCapturePolicyValidator validator;

  AmbientCapturePolicy policy({
    String pluginId = 'ambient_second_brain_controller',
    String userId = 'user-1',
    String deviceId = 'device-1',
    int sequence = 2,
    DateTime? validUntil,
    bool allowAccessibilityMode = false,
    bool allowCaptionFallback = false,
  }) {
    final now = DateTime.utc(2026, 1, 1, 12);
    return AmbientCapturePolicy.fromJson({
      'version': 1,
      'plugin_id': pluginId,
      'scope': 'ambient_capture_controller',
      'user_id': userId,
      'device_id': deviceId,
      'sequence': sequence,
      'issued_at': now.subtract(const Duration(minutes: 1)).toIso8601String(),
      'valid_until': (validUntil ?? now.add(const Duration(hours: 1))).toIso8601String(),
      'capture_mode': 'normal',
      'sensitivity': 'medium',
      'silence_detection_seconds': 12,
      'rms_silence_dbfs_threshold': -75,
      'zero_frame_threshold': 0.98,
      'allow_foreground_mic': true,
      'allow_accessibility_mode': allowAccessibilityMode,
      'allow_local_stt_fallback': false,
      'allow_caption_fallback': allowCaptionFallback,
      'allow_audio_upload': false,
      'allow_transcript_upload': true,
      'raw_audio_retention': 'none',
      'communication_mode': 'detect_only',
      'high_risk_apps': ['us.zoom.videomeetings'],
      'notification_aggressiveness': 'quiet',
      'audit_level': 'basic',
    });
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'advanced_ambient_capture_enabled': true,
      'ambient_capture_plugin_control_enabled': true,
    });
    await SharedPreferencesUtil.init();
    validator = AmbientCapturePolicyValidator();
  });

  test('accepts valid policy', () {
    final decision = validator.validate(
      policy: policy(),
      expectedPluginId: 'ambient_second_brain_controller',
      expectedUserId: 'user-1',
      expectedDeviceId: 'device-1',
      lastSequence: 1,
      accessibilityEnabled: false,
      now: DateTime.utc(2026, 1, 1, 12),
    );
    expect(decision.accepted, isTrue);
  });

  test('expired policy rejected', () {
    final decision = validator.validate(
      policy: policy(validUntil: DateTime.utc(2026, 1, 1, 11)),
      expectedPluginId: 'ambient_second_brain_controller',
      expectedUserId: 'user-1',
      expectedDeviceId: 'device-1',
      lastSequence: 1,
      accessibilityEnabled: false,
      now: DateTime.utc(2026, 1, 1, 12),
    );
    expect(decision.reason, 'expired');
  });

  test('wrong plugin rejected', () {
    final decision = validator.validate(
      policy: policy(pluginId: 'other'),
      expectedPluginId: 'ambient_second_brain_controller',
      expectedUserId: 'user-1',
      expectedDeviceId: 'device-1',
      lastSequence: 1,
      accessibilityEnabled: false,
      now: DateTime.utc(2026, 1, 1, 12),
    );
    expect(decision.reason, 'wrong_plugin');
  });

  test('wrong user and device rejected', () {
    expect(
      validator
          .validate(
            policy: policy(userId: 'other'),
            expectedPluginId: 'ambient_second_brain_controller',
            expectedUserId: 'user-1',
            expectedDeviceId: 'device-1',
            lastSequence: 1,
            accessibilityEnabled: false,
            now: DateTime.utc(2026, 1, 1, 12),
          )
          .reason,
      'wrong_user',
    );
    expect(
      validator
          .validate(
            policy: policy(deviceId: 'other'),
            expectedPluginId: 'ambient_second_brain_controller',
            expectedUserId: 'user-1',
            expectedDeviceId: 'device-1',
            lastSequence: 1,
            accessibilityEnabled: false,
            now: DateTime.utc(2026, 1, 1, 12),
          )
          .reason,
      'wrong_device',
    );
  });

  test('private mode override rejects capture policy', () {
    final decision = validator.validate(
      policy: policy(),
      expectedPluginId: 'ambient_second_brain_controller',
      expectedUserId: 'user-1',
      expectedDeviceId: 'device-1',
      lastSequence: 1,
      accessibilityEnabled: false,
      privateModeActive: true,
      now: DateTime.utc(2026, 1, 1, 12),
    );
    expect(decision.reason, 'private_mode_active');
  });

  test('policy cannot enable accessibility or caption fallback when local settings are off', () {
    final decision = validator.validate(
      policy: policy(allowAccessibilityMode: true, allowCaptionFallback: true),
      expectedPluginId: 'ambient_second_brain_controller',
      expectedUserId: 'user-1',
      expectedDeviceId: 'device-1',
      lastSequence: 1,
      accessibilityEnabled: false,
      now: DateTime.utc(2026, 1, 1, 12),
    );

    final prefs = SharedPreferencesUtil();
    expect(decision.accepted, isTrue);
    expect(prefs.ambientCaptureAccessibilityModeEnabled, isFalse);
    expect(prefs.ambientCaptureCaptionFallbackEnabled, isFalse);
  });

  test('capture health state model parses degraded states', () {
    final health = AmbientCaptureHealth.fromJson({
      'state': 'AUDIO_SILENCED_BY_SYSTEM',
      'dbfs': -120,
      'zeroFrameRatio': 1.0,
      'networkAvailable': false,
      'socketConnected': false,
      'walQueueDepth': 12,
      'timestamp': 1767225600000,
    });

    expect(health.state, AmbientCaptureHealthState.audioSilencedBySystem);
    expect(health.zeroFrameRatio, 1.0);
    expect(health.walQueueDepth, 12);
  });
}
