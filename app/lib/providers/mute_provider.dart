import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

/// Provider that manages the microphone mute functionality
/// Supports both immediate mute/unmute and timed mute duration
class MuteProvider extends ChangeNotifier {
  bool _isMuted = false;
  bool _isTimerMuteActive = false;
  Timer? _muteTimer;
  DateTime? _muteStartTime;
  Duration? _muteDuration;

  /// Whether the microphone is currently muted (either manually or by timer)
  bool get isMuted => _isMuted || _isTimerMuteActive;

  /// Whether the manual mute toggle is active
  bool get isManuallyMuted => _isMuted;

  /// Whether the timer mute is currently active
  bool get isTimerMuteActive => _isTimerMuteActive;

  /// The time when mute was started (for timer functionality)
  DateTime? get muteStartTime => _muteStartTime;

  /// The duration for which the mic is muted
  Duration? get muteDuration => _muteDuration;

  /// Time remaining for timer mute
  Duration? get timeRemaining {
    if (!_isTimerMuteActive || _muteStartTime == null || _muteDuration == null) {
      return null;
    }

    final elapsed = DateTime.now().difference(_muteStartTime!);
    final remaining = _muteDuration! - elapsed;
    return remaining.isNegative ? Duration.zero : remaining;
  }

  MuteProvider() {
    // Load persisted mute state
    _loadMuteState();
  }

  /// Load mute state from preferences
  void _loadMuteState() {
    _isMuted = SharedPreferencesUtil().microphoneMuted;
  }

  /// Save mute state to preferences
  void _saveMuteState() {
    SharedPreferencesUtil().microphoneMuted = _isMuted;
  }

  /// Toggle the manual mute state
  void toggleMute() {
    // If timer mute is active, cancel it and set to unmuted
    if (_isTimerMuteActive) {
      _cancelTimerMute();
      _isMuted = false;
    } else {
      // Normal toggle behavior when no timer is active
      _isMuted = !_isMuted;
    }

    _saveMuteState();

    // Analytics tracking
    MixpanelManager().track('Microphone Mute Toggled', properties: {
      'is_muted': _isMuted,
      'mute_type': 'manual',
    });

    debugPrint('Microphone ${_isMuted ? "muted" : "unmuted"} manually');
    notifyListeners();
  }

  /// Mute the microphone for a specific duration
  void muteForDuration(Duration duration) {
    _isTimerMuteActive = true;
    _muteStartTime = DateTime.now();
    _muteDuration = duration;

    // Cancel any existing timer
    _muteTimer?.cancel();

    // Start new timer
    _muteTimer = Timer(duration, () {
      _unmuteFromTimer();
    });

    // Analytics tracking
    MixpanelManager().track('Microphone Timed Mute Started', properties: {
      'duration_minutes': duration.inMinutes,
    });

    debugPrint('Microphone muted for ${duration.inMinutes} minutes');
    notifyListeners();
  }

  /// Cancel the timer mute
  void _cancelTimerMute() {
    if (_isTimerMuteActive) {
      _muteTimer?.cancel();
      _isTimerMuteActive = false;
      _muteStartTime = null;
      _muteDuration = null;

      MixpanelManager().track('Microphone Timed Mute Cancelled');
      debugPrint('Timer mute cancelled');
    }
  }

  /// Called when timer expires to unmute
  void _unmuteFromTimer() {
    _isTimerMuteActive = false;
    _muteStartTime = null;
    _muteDuration = null;

    MixpanelManager().track('Microphone Timed Mute Expired');
    debugPrint('Timer mute expired - microphone unmuted');
    notifyListeners();
  }

  /// Manually cancel timer mute (exposed for UI)
  void cancelTimerMute() {
    _cancelTimerMute();
    notifyListeners();
  }

  /// Unmute everything (both manual and timer)
  void unmuteAll() {
    _isMuted = false;
    _cancelTimerMute();
    _saveMuteState();

    MixpanelManager().track('Microphone Unmuted All');
    debugPrint('Microphone unmuted (all mutes cleared)');
    notifyListeners();
  }

  @override
  void dispose() {
    _muteTimer?.cancel();
    super.dispose();
  }
}
