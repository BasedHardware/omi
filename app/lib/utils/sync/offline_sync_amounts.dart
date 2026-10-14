import 'package:omi/models/sync_state.dart';
import 'package:omi/services/wals/wal.dart';

/// Offline Sync measures work in seconds of audio, never in files.
///
/// Capture writes a file every 75 s and the device hands storage over in fixed
/// chunks, so a file count ("0/5914") says nothing a person can act on, and it
/// changed meaning at every step: device bytes, then upload files, then server
/// jobs. Every number on the page now comes from here, in one unit.

bool walIsOnDevice(Wal wal) => wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;

int walSeconds(Iterable<Wal> wals) => wals.fold(0, (sum, w) => sum + (w.seconds > 0 ? w.seconds : 0));

/// Recordings that will still move forward on their own or with a tap. Terminal
/// states (too old, unreadable, refused) are excluded: they need the user, not time.
bool walIsSyncable(Wal wal) => switch (wal.syncDisplayState) {
      WalSyncDisplayState.waiting || WalSyncDisplayState.syncing || WalSyncDisplayState.retrying => true,
      WalSyncDisplayState.failed => true,
      _ => false,
    };

/// Where unsynced audio is sitting right now. Drives the Sync details sheet.
class SyncPipelineAmounts {
  const SyncPipelineAmounts({
    required this.onDeviceSeconds,
    required this.onDeviceBytes,
    required this.onPhoneSeconds,
    required this.processingSeconds,
  });

  factory SyncPipelineAmounts.of(Iterable<Wal> wals) {
    var onDeviceSeconds = 0, onDeviceBytes = 0, onPhoneSeconds = 0, processingSeconds = 0;
    for (final w in wals) {
      final seconds = w.seconds > 0 ? w.seconds : 0;
      if (w.status == WalStatus.uploaded) {
        processingSeconds += seconds;
      } else if (w.status == WalStatus.miss && walIsSyncable(w)) {
        if (walIsOnDevice(w)) {
          onDeviceSeconds += seconds;
          final remaining = w.storageTotalBytes - w.storageOffset;
          if (remaining > 0) onDeviceBytes += remaining;
        } else {
          onPhoneSeconds += seconds;
        }
      }
    }
    return SyncPipelineAmounts(
      onDeviceSeconds: onDeviceSeconds,
      onDeviceBytes: onDeviceBytes,
      onPhoneSeconds: onPhoneSeconds,
      processingSeconds: processingSeconds,
    );
  }

  final int onDeviceSeconds;
  final int onDeviceBytes;
  final int onPhoneSeconds;
  final int processingSeconds;
}

/// The three steps of a sync, in order. The status card draws one bar segment
/// per step, so progress fills left to right and never restarts at 0%.
enum SyncStep { download, upload, transcribe }

/// Progress of the active step, in seconds of audio.
class SyncStepProgress {
  const SyncStepProgress({
    required this.step,
    required this.doneSeconds,
    required this.totalSeconds,
    SyncStep? barStep,
  }) : barStep = barStep ?? step;

  /// The step the provider is running, which the subtitle describes.
  final SyncStep step;

  /// The bar segment to draw as active. It never moves backwards within a run,
  /// and stays on [SyncStep.download] while audio is still waiting on the
  /// device: a sync uploads live-capture files before it drains the device.
  final SyncStep barStep;
  final int doneSeconds;
  final int totalSeconds;

  double get fraction => totalSeconds <= 0 ? 0 : (doneSeconds / totalSeconds).clamp(0.0, 1.0);
}

/// Remembers what an active sync set out to move, so its numbers hold still.
///
/// Totals are taken when a run or a step is first seen: a recording that
/// finishes uploading leaves the "waiting on this phone" set, and a live total
/// would shrink under the bar instead of the bar filling. Upload progress is
/// the seconds of that snapshot now uploaded, so a 40 min recording weighs
/// more than an 18 s one; the device reports only a byte fraction for its
/// drain, which is applied to the snapshot's seconds.
class SyncRunTracker {
  int? _runSeconds;
  SyncStep? _stepKey;
  Set<String> _stepIds = const {};
  int _stepSeconds = 0;
  int _doneHighWater = 0;
  SyncStep? _barStep;

  /// Seconds of audio the current run set out to sync; null when idle.
  int? get runSeconds => _runSeconds;

  static String _key(Wal w) => '${w.id}#${w.storage.name}';

  static SyncStep _stepOf(SyncPhase phase) => switch (phase) {
        SyncPhase.downloadingFromDevice => SyncStep.download,
        SyncPhase.uploadingToCloud || SyncPhase.waitingForInternet => SyncStep.upload,
        SyncPhase.processingOnServer || SyncPhase.idle => SyncStep.transcribe,
      };

  /// Call on every build. Returns null when no sync is running.
  SyncStepProgress? update(SyncState state, List<Wal> wals) {
    final active = state.isSyncing || state.isFetchingConversations;
    if (!active) {
      _runSeconds = null;
      _stepKey = null;
      _stepIds = const {};
      _stepSeconds = 0;
      _doneHighWater = 0;
      _barStep = null;
      return null;
    }

    // Grows when device discovery lands after the first frame; never shrinks
    // as recordings finish.
    final pending = walSeconds(wals.where((w) => w.status == WalStatus.miss && walIsSyncable(w)));
    if (_runSeconds == null || pending > _runSeconds!) _runSeconds = pending;

    final step = _stepOf(state.phase);
    if (step != _stepKey) {
      _stepKey = step;
      final members = switch (step) {
        SyncStep.download => wals.where((w) => walIsOnDevice(w) && w.status == WalStatus.miss),
        SyncStep.upload => wals.where((w) => !walIsOnDevice(w) && w.status == WalStatus.miss && walIsSyncable(w)),
        SyncStep.transcribe => const <Wal>[],
      };
      _stepIds = members.map(_key).toSet();
      _stepSeconds = walSeconds(members);
      _doneHighWater = 0;
    }

    final deviceStillHolds = wals.any((w) => walIsOnDevice(w) && w.status == WalStatus.miss && walIsSyncable(w));
    final natural = step == SyncStep.upload && deviceStillHolds ? SyncStep.download : step;
    final barStep = _barStep == null || natural.index > _barStep!.index ? natural : _barStep!;
    _barStep = barStep;

    int done;
    switch (step) {
      case SyncStep.download:
        // The device restarts its fraction per file and per storage; keep the high-water mark.
        done = (state.progress.clamp(0.0, 1.0) * _stepSeconds).round();
      case SyncStep.upload:
        done = walSeconds(wals.where(
          (w) => _stepIds.contains(_key(w)) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced),
        ));
      case SyncStep.transcribe:
        return SyncStepProgress(step: step, doneSeconds: 0, totalSeconds: 0, barStep: barStep);
    }
    if (done > _stepSeconds) done = _stepSeconds;
    if (done < _doneHighWater) done = _doneHighWater;
    _doneHighWater = done;
    return SyncStepProgress(step: step, doneSeconds: done, totalSeconds: _stepSeconds, barStep: barStep);
  }
}
