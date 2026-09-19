import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/services/capture/capture_seams.dart';

/// [release] untracks the callback and starts cancel once; [CaptureLifetime.close]
/// still joins that cancellation until it actually finishes.
class CaptureOwned {
  CaptureOwned._(this._release);
  final Future<void> Function() _release;
  Future<void> release() => _release();
}

/// Every timer/subscription/listener created by the capture owner is registered
/// here immediately, including resources acquired after asynchronous work.
class CaptureLifetime implements CaptureScheduling {
  CaptureLifetime(this._scheduling);

  final CaptureScheduling _scheduling;
  final List<FutureOr<void> Function()> _releases = [];
  final Set<Future<void>> _inflightCancels = {};
  bool _closed = false;
  Future<void>? _closing;
  bool _closeFinished = false;

  @visibleForTesting
  int get debugTrackedCount => _releases.length;

  bool get isClosed => _closed;

  Future<void> _watchCancel(FutureOr<void> work) {
    final pending = Future<void>.sync(() async {
      await work;
    });
    _inflightCancels.add(pending);
    return pending.whenComplete(() => _inflightCancels.remove(pending));
  }

  void _untrack(FutureOr<void> Function() release) => _releases.remove(release);

  void _track(FutureOr<void> Function() release) {
    if (_closed) {
      unawaited(Future.sync(release));
      return;
    }
    _releases.add(release);
  }

  _LifetimeTimer _wrap(Timer inner, FutureOr<void> Function() release) {
    _track(release);
    return _LifetimeTimer(inner, () => _untrack(release));
  }

  @override
  Timer once(Duration delay, void Function() callback) {
    late final FutureOr<void> Function() release;
    late final Timer inner;
    inner = _scheduling.once(delay, () {
      _untrack(release);
      if (_closed) return;
      callback();
    });
    release = inner.cancel;
    return _wrap(inner, release);
  }

  @override
  Timer periodic(Duration interval, void Function(Timer) callback) {
    late final FutureOr<void> Function() release;
    late final _LifetimeTimer wrapper;
    late final Timer inner;
    inner = _scheduling.periodic(interval, (_) {
      if (_closed) return;
      callback(wrapper);
    });
    release = inner.cancel;
    wrapper = _wrap(inner, release);
    return wrapper;
  }

  StreamSubscription<T> listen<T>(
    Stream<T> stream,
    void Function(T) onData, {
    Function? onError,
    void Function()? onDone,
    bool cancelOnError = false,
  }) {
    late final FutureOr<void> Function() release;
    var live = true;
    void drop() {
      live = false;
      _untrack(release);
    }

    bool isClosed() => _closed;
    final inner = stream.listen(
      (value) {
        if (_closed) return;
        onData(value);
      },
      onError: (Object error, StackTrace stack) {
        if (cancelOnError) drop();
        if (_closed) return;
        _forwardError(onError, error, stack);
      },
      onDone: () {
        drop();
        if (_closed) return;
        onDone?.call();
      },
      cancelOnError: cancelOnError,
    );
    release = () {
      if (!live) return null;
      live = false;
      _untrack(release);
      return _watchCancel(inner.cancel());
    };
    _track(release);
    return _LifetimeSubscription<T>(inner, drop, isClosed, () => Future.sync(release), cancelOnError: cancelOnError);
  }

  CaptureOwned own(FutureOr<void> Function() cancel) {
    var live = true;
    late final FutureOr<void> Function() release;
    release = () {
      if (!live) return null;
      live = false;
      _untrack(release);
      return _watchCancel(cancel());
    };
    _track(release);
    return CaptureOwned._(() async {
      await Future.sync(release);
    });
  }

  /// Replace [previous] with [next]. A closed lifetime cancels [next] immediately.
  StreamSubscription? takeSubscription(StreamSubscription? previous, StreamSubscription? next) {
    previous?.cancel();
    if (next == null) return null;
    if (_closed) {
      next.cancel();
      return null;
    }
    return next;
  }

  Future<void> close() {
    _closed = true;
    if (_closeFinished) return Future<void>.value();
    return _closing ??= _drain();
  }

  Future<void> _drain() async {
    final releases = List<FutureOr<void> Function()>.of(_releases);
    _releases.clear();
    Object? error;
    StackTrace? stack;
    try {
      for (final release in releases) {
        try {
          await Future.sync(release);
        } catch (caught, caughtStack) {
          error ??= caught;
          stack ??= caughtStack;
        }
      }
      // An unregistered callback is not unfinished teardown: join explicit
      // cancel/release futures that already left the bag.
      for (final pending in List<Future<void>>.of(_inflightCancels)) {
        try {
          await pending;
        } catch (caught, caughtStack) {
          error ??= caught;
          stack ??= caughtStack;
        }
      }
      if (error != null) Error.throwWithStackTrace(error, stack!);
    } finally {
      _closeFinished = true;
    }
  }
}

void _forwardError(Function? onError, Object error, StackTrace stack) {
  if (onError is void Function(Object, StackTrace)) {
    onError(error, stack);
  } else if (onError is void Function(Object)) {
    onError(error);
  } else if (onError != null) {
    onError(error, stack);
  } else {
    Zone.current.handleUncaughtError(error, stack);
  }
}

class _LifetimeTimer implements Timer {
  _LifetimeTimer(this._inner, this._drop);
  final Timer _inner;
  final void Function() _drop;
  @override
  void cancel() {
    _drop();
    _inner.cancel();
  }

  @override
  bool get isActive => _inner.isActive;
  @override
  int get tick => _inner.tick;
}

class _LifetimeSubscription<T> implements StreamSubscription<T> {
  _LifetimeSubscription(this._inner, this._drop, this._isClosed, this._cancel, {this.cancelOnError = false});
  final StreamSubscription<T> _inner;
  final void Function() _drop;
  final bool Function() _isClosed;
  final Future<void> Function() _cancel;
  final bool cancelOnError;
  @override
  Future<void> cancel() => _cancel();

  @override
  void onData(void Function(T)? handleData) {
    _inner.onData(
      handleData == null
          ? null
          : (value) {
              if (_isClosed()) return;
              handleData(value);
            },
    );
  }

  @override
  void onError(Function? handleError) {
    _inner.onError((Object error, StackTrace stack) {
      if (cancelOnError) _drop();
      if (_isClosed()) return;
      _forwardError(handleError, error, stack);
    });
  }

  @override
  void onDone(void Function()? handleDone) => _inner.onDone(() {
        _drop();
        if (_isClosed()) return;
        handleDone?.call();
      });
  @override
  void pause([Future<void>? resumeSignal]) => _inner.pause(resumeSignal);
  @override
  void resume() => _inner.resume();
  @override
  bool get isPaused => _inner.isPaused;
  @override
  Future<E> asFuture<E>([E? futureValue]) => _inner.asFuture<E>(futureValue).whenComplete(_drop);
}
