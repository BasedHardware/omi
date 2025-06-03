import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/mute_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('MuteProvider Tests', () {
    late MuteProvider muteProvider;

    setUp(() async {
      // Initialize SharedPreferences for testing
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      muteProvider = MuteProvider();
    });

    tearDown(() {
      muteProvider.dispose();
    });

    test('should initialize with unmuted state', () {
      expect(muteProvider.isMuted, false);
      expect(muteProvider.isManuallyMuted, false);
      expect(muteProvider.isTimerMuteActive, false);
    });

    test('should toggle mute state correctly', () {
      // Initially unmuted
      expect(muteProvider.isMuted, false);

      // Toggle to muted
      muteProvider.toggleMute();
      expect(muteProvider.isMuted, true);
      expect(muteProvider.isManuallyMuted, true);

      // Toggle back to unmuted
      muteProvider.toggleMute();
      expect(muteProvider.isMuted, false);
      expect(muteProvider.isManuallyMuted, false);
    });

    test('should persist mute state in preferences', () {
      // Toggle mute
      muteProvider.toggleMute();
      expect(SharedPreferencesUtil().microphoneMuted, true);

      // Toggle back
      muteProvider.toggleMute();
      expect(SharedPreferencesUtil().microphoneMuted, false);
    });

    test('should handle timer mute correctly', () async {
      const duration = Duration(milliseconds: 100);

      // Start timer mute
      muteProvider.muteForDuration(duration);

      expect(muteProvider.isMuted, true);
      expect(muteProvider.isTimerMuteActive, true);
      expect(muteProvider.muteStartTime, isNotNull);
      expect(muteProvider.muteDuration, equals(duration));

      // Wait for timer to expire
      await Future.delayed(const Duration(milliseconds: 150));

      expect(muteProvider.isMuted, false);
      expect(muteProvider.isTimerMuteActive, false);
    });

    test('should calculate time remaining correctly', () {
      const duration = Duration(minutes: 5);

      muteProvider.muteForDuration(duration);

      final timeRemaining = muteProvider.timeRemaining;
      expect(timeRemaining, isNotNull);
      expect(timeRemaining!.inMinutes, lessThanOrEqualTo(5));
      expect(timeRemaining.inMinutes, greaterThanOrEqualTo(4));
    });

    test('should cancel timer mute when manually unmuting', () {
      const duration = Duration(minutes: 5);

      // Start timer mute
      muteProvider.muteForDuration(duration);
      expect(muteProvider.isTimerMuteActive, true);

      // Manually toggle (should cancel timer)
      muteProvider.toggleMute();
      expect(muteProvider.isTimerMuteActive, false);
      expect(muteProvider.isMuted, false);
    });

    test('should cancel timer mute manually', () {
      const duration = Duration(minutes: 5);

      // Start timer mute
      muteProvider.muteForDuration(duration);
      expect(muteProvider.isTimerMuteActive, true);

      // Cancel timer mute
      muteProvider.cancelTimerMute();
      expect(muteProvider.isTimerMuteActive, false);
      expect(muteProvider.isMuted, false);
    });

    test('should unmute all correctly', () {
      const duration = Duration(minutes: 5);

      // Set both manual and timer mute
      muteProvider.toggleMute(); // Manual mute
      muteProvider.muteForDuration(duration); // Timer mute

      expect(muteProvider.isMuted, true);
      expect(muteProvider.isManuallyMuted, true);
      expect(muteProvider.isTimerMuteActive, true);

      // Unmute all
      muteProvider.unmuteAll();

      expect(muteProvider.isMuted, false);
      expect(muteProvider.isManuallyMuted, false);
      expect(muteProvider.isTimerMuteActive, false);
      expect(SharedPreferencesUtil().microphoneMuted, false);
    });

    test('should handle multiple timer mute calls correctly', () {
      const duration1 = Duration(minutes: 5);
      const duration2 = Duration(minutes: 10);

      // Start first timer
      muteProvider.muteForDuration(duration1);
      final firstStartTime = muteProvider.muteStartTime;

      // Start second timer (should cancel first)
      muteProvider.muteForDuration(duration2);
      final secondStartTime = muteProvider.muteStartTime;

      expect(muteProvider.isTimerMuteActive, true);
      expect(muteProvider.muteDuration, equals(duration2));
      expect(secondStartTime, isNot(equals(firstStartTime)));
    });

    test('should return null time remaining when not timer muted', () {
      expect(muteProvider.timeRemaining, isNull);

      // Manual mute should still return null
      muteProvider.toggleMute();
      expect(muteProvider.timeRemaining, isNull);
    });
  });
}
