import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';

class MicrophoneProvider extends ChangeNotifier {
  bool _isMuted = false;
  Timer? _autoUnmuteTimer;
  DateTime? _muteStartTime;
  int? _muteDurationMinutes;

  bool get isMuted => _isMuted;
  bool get hasAutoUnmuteTimer => _autoUnmuteTimer != null;
  DateTime? get muteStartTime => _muteStartTime;
  int? get muteDurationMinutes => _muteDurationMinutes;

  MicrophoneProvider() {
    // Load saved mute state on initialization
    _loadMuteState();
  }

  void _loadMuteState() {
    // Load mute state from preferences if needed
    // For now, we'll start unmuted by default
    _isMuted = false;
  }

  void toggleMute() {
    if (_isMuted) {
      unmute();
    } else {
      mute();
    }
  }

  void mute({int? durationMinutes}) {
    _isMuted = true;
    _muteStartTime = DateTime.now();
    _muteDurationMinutes = durationMinutes;

    // Cancel any existing timer
    _autoUnmuteTimer?.cancel();

    // Set up auto-unmute timer if duration is specified
    if (durationMinutes != null && durationMinutes > 0) {
      _autoUnmuteTimer = Timer(Duration(minutes: durationMinutes), () {
        unmute();
      });
    }

    debugPrint('Microphone muted${durationMinutes != null ? ' for $durationMinutes minutes' : ''}');
    notifyListeners();
  }

  void unmute() {
    _isMuted = false;
    _muteStartTime = null;
    _muteDurationMinutes = null;

    // Cancel auto-unmute timer
    _autoUnmuteTimer?.cancel();
    _autoUnmuteTimer = null;

    debugPrint('Microphone unmuted');
    notifyListeners();
  }

  String getMuteStatusText() {
    if (!_isMuted) return '';

    if (_muteDurationMinutes != null && _muteStartTime != null) {
      final elapsed = DateTime.now().difference(_muteStartTime!);
      final remaining = Duration(minutes: _muteDurationMinutes!) - elapsed;

      if (remaining.inMinutes > 0) {
        return 'Muted for ${remaining.inMinutes}m';
      } else {
        return 'Muted';
      }
    }

    return 'Muted';
  }

  int getRemainingMuteMinutes() {
    if (!_isMuted || _muteDurationMinutes == null || _muteStartTime == null) {
      return 0;
    }

    final elapsed = DateTime.now().difference(_muteStartTime!);
    final remaining = Duration(minutes: _muteDurationMinutes!) - elapsed;
    return remaining.inMinutes.clamp(0, _muteDurationMinutes!);
  }

  @override
  void dispose() {
    _autoUnmuteTimer?.cancel();
    super.dispose();
  }
}
