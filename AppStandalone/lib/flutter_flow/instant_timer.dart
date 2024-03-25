import 'dart:async';

extension TimerExt on Timer? {
  bool get isActive => this?.isActive ?? false;
  int get tick => this?.tick ?? 0;
}

class InstantTimer implements Timer {
  factory InstantTimer.periodic({
    required Duration duration,
    required void Function(Timer timer) callback,
    bool startImmediately = true,
  }) {
    final myTimer = Timer.periodic(duration, callback);
    if (startImmediately) {
      Future.delayed(const Duration(seconds: 0)).then((_) => callback(myTimer));
    }
    return InstantTimer._(myTimer, startImmediately);
  }

  InstantTimer._(this._timer, this._startImmediately);
  final Timer _timer;
  final bool _startImmediately;

  @override
  void cancel() {
    _timer.cancel();
  }

  @override
  bool get isActive => _timer.isActive;

  @override
  int get tick => _timer.tick + (_startImmediately ? 1 : 0);
}
