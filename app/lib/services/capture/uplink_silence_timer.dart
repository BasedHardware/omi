import 'dart:async';

import 'package:omi/services/capture/capture_seams.dart';

/// Wall-clock silence is measured from capture start or the latest speech
/// transcript, never from BLE packets (which also contain silence).
class UplinkSilenceTimer {
  UplinkSilenceTimer({required this.scheduling, required this.now, required this.timeout, required this.onTimeout});

  /// Match the listen server's existing settings contract: -1 is four hours,
  /// and malformed/sub-minimum values retain the two-minute floor.
  static Duration fromPreference(int seconds) =>
      Duration(seconds: seconds == -1 ? 4 * 60 * 60 : (seconds < 120 ? 120 : seconds));

  final CaptureScheduling scheduling;
  final DateTime Function() now;
  final Duration Function() timeout;
  final void Function() onTimeout;
  Timer? _timer;
  DateTime? _deadline;

  bool get expired => _deadline != null && !now().isBefore(_deadline!);

  void speechOrStart() {
    cancel();
    final duration = timeout();
    _deadline = now().add(duration);
    _timer = scheduling.once(duration, onTimeout);
  }

  void cancel() {
    _timer?.cancel();
    _timer = null;
    _deadline = null;
  }
}
