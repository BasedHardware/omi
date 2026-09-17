import 'dart:async';

import 'package:omi/services/capture/capture_seams.dart';

/// Every timer/subscription/listener created by the capture owner is registered
/// here immediately, including resources acquired after asynchronous work.
class CaptureLifetime implements CaptureScheduling {
  CaptureLifetime(this._scheduling);

  final CaptureScheduling _scheduling;
  final List<FutureOr<void> Function()> _releases = [];
  bool _closed = false;

  void _track(FutureOr<void> Function() release) {
    if (_closed) {
      unawaited(Future.sync(release));
      return;
    }
    _releases.add(release);
  }

  @override
  Timer once(Duration delay, void Function() callback) {
    late final Timer timer;
    timer = _scheduling.once(delay, () {
      if (_closed) return;
      callback();
    });
    _track(timer.cancel);
    return timer;
  }

  @override
  Timer periodic(Duration interval, void Function(Timer) callback) {
    late final Timer timer;
    timer = _scheduling.periodic(interval, (tick) {
      if (_closed) return;
      callback(tick);
    });
    _track(timer.cancel);
    return timer;
  }

  StreamSubscription<T> listen<T>(Stream<T> stream, void Function(T) onData) {
    final subscription = stream.listen((value) {
      if (_closed) return;
      onData(value);
    });
    _track(subscription.cancel);
    return subscription;
  }

  void own(FutureOr<void> Function() cancel) => _track(cancel);

  Future<void> close() async {
    _closed = true;
    final releases = List<FutureOr<void> Function()>.of(_releases);
    _releases.clear();
    Object? error;
    StackTrace? stack;
    for (final release in releases) {
      try {
        await Future.sync(release);
      } catch (caught, caughtStack) {
        error ??= caught;
        stack ??= caughtStack;
      }
    }
    if (error != null) {
      Error.throwWithStackTrace(error, stack!);
    }
  }
}
