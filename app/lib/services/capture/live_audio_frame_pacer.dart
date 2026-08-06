import 'dart:async';
import 'dart:collection';

class LiveAudioFrameDelivery {
  const LiveAudioFrameDelivery._({
    required this.accepted,
    required this.completed,
  });

  final bool accepted;
  final Future<bool> completed;

  factory LiveAudioFrameDelivery.rejected() => LiveAudioFrameDelivery._(
        accepted: false,
        completed: Future<bool>.value(false),
      );

  factory LiveAudioFrameDelivery.accepted(Future<bool> completed) => LiveAudioFrameDelivery._(
        accepted: true,
        completed: completed,
      );
}

class _PendingLiveAudioBatch {
  _PendingLiveAudioBatch(List<List<int>> frames) : frames = frames.map(List<int>.from).toList(growable: false);

  final List<List<int>> frames;
  final Completer<bool> completer = Completer<bool>();
  int nextFrame = 0;

  int get remainingFrames => frames.length - nextFrame;
}

/// Delivers storage-backed audio at the cadence encoded by the negotiated
/// codec instead of dumping a completed BLE read into the live STT socket.
///
/// The pendant/phone WAL remains the durable source of truth. This queue owns
/// only the low-latency preview lane. A batch is complete only after every
/// frame has entered the socket; rejection leaves its durable WAL retryable.
class LiveAudioFramePacer {
  LiveAudioFramePacer({
    required this.framesPerSecond,
    required this.canSend,
    required this.send,
    this.maxBufferedSeconds = 120,
  })  : assert(framesPerSecond > 0),
        assert(maxBufferedSeconds > 0);

  final int framesPerSecond;
  final bool Function() canSend;
  final void Function(List<int> frame) send;
  final int maxBufferedSeconds;

  final ListQueue<_PendingLiveAudioBatch> _batches = ListQueue<_PendingLiveAudioBatch>();
  Timer? _timer;
  int _bufferedFrames = 0;

  int get bufferedFrames => _bufferedFrames;
  bool get isActive => _timer?.isActive ?? false;

  /// Accepts one immutable WAL batch for live preview.
  ///
  /// [LiveAudioFrameDelivery.completed] resolves true only after the final
  /// frame was sent. A socket loss or explicit reset resolves every pending
  /// batch false; callers must retain those WALs for replay/canonical repair.
  LiveAudioFrameDelivery enqueue(List<List<int>> frames) {
    final nonEmptyFrames = frames.where((frame) => frame.isNotEmpty).toList();
    if (nonEmptyFrames.isEmpty) {
      return LiveAudioFrameDelivery.accepted(Future<bool>.value(true));
    }
    if (!canSend()) {
      rejectPending();
      return LiveAudioFrameDelivery.rejected();
    }

    final maximumFrames = framesPerSecond * maxBufferedSeconds;
    if (_bufferedFrames + nonEmptyFrames.length > maximumFrames) {
      return LiveAudioFrameDelivery.rejected();
    }

    final batch = _PendingLiveAudioBatch(nonEmptyFrames);
    _batches.add(batch);
    _bufferedFrames += batch.remainingFrames;
    _start();
    return LiveAudioFrameDelivery.accepted(batch.completer.future);
  }

  void _start() {
    if (_batches.isEmpty || _timer?.isActive == true) return;
    final interval = Duration(
      microseconds: (Duration.microsecondsPerSecond / framesPerSecond).round(),
    );
    _timer = Timer.periodic(interval, (_) {
      if (!canSend()) {
        rejectPending();
        return;
      }
      if (_batches.isEmpty) {
        _timer?.cancel();
        _timer = null;
        return;
      }

      final batch = _batches.first;
      send(batch.frames[batch.nextFrame]);
      batch.nextFrame += 1;
      _bufferedFrames -= 1;
      if (batch.remainingFrames == 0) {
        _batches.removeFirst();
        if (!batch.completer.isCompleted) batch.completer.complete(true);
      }
    });
  }

  void rejectPending() {
    _timer?.cancel();
    _timer = null;
    while (_batches.isNotEmpty) {
      final batch = _batches.removeFirst();
      if (!batch.completer.isCompleted) batch.completer.complete(false);
    }
    _bufferedFrames = 0;
  }

  void reset() => rejectPending();

  void dispose() => rejectPending();
}
