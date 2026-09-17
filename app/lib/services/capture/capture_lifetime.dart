import 'dart:async';

import 'package:omi/services/capture/capture_seams.dart';

/// Every timer/subscription/listener created by the capture owner is registered
/// here immediately, including resources acquired after asynchronous work.
class CaptureLifetime implements CaptureScheduling {
  CaptureLifetime(CaptureScheduling scheduling);

  @override
  Timer once(Duration delay, void Function() callback) => throw UnimplementedError('C1 owned timer');
  @override
  Timer periodic(Duration interval, void Function(Timer) callback) => throw UnimplementedError('C1 owned timer');
  int get debugTrackedCount => throw UnimplementedError('C1 active registration inventory');
  StreamSubscription<T> listen<T>(Stream<T> stream, void Function(T) onData,
          {Function? onError, void Function()? onDone, bool? cancelOnError}) =>
      throw UnimplementedError('C1 owned subscription');
  void own(FutureOr<void> Function() cancel) => throw UnimplementedError('C1 owned listener removal');
  Future<void> close() => throw UnimplementedError('C1 idempotent disposal');
}
