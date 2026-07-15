import 'dart:async';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/logger.dart';

/// Called with the conversation ids surfaced by a reconcile pass so the
/// presentation layer can fetch + show them. Provided by the provider so this
/// service never imports upward (services must not depend on providers).
typedef ConversationSurfaceCallback = Future<void> Function(SyncLocalFilesResponse result);

/// Drives [LocalWalSyncImpl.reconcileUploadedWals] off the upload critical
/// path. [RecordingTransferCoordinator] owns when a pass runs; this service
/// remains the callee that resolves already-uploaded server jobs.
///
/// All state lives in the persisted WAL list, so this survives navigation and
/// app-kill — a fresh process just `poke`s on startup and resumes. Scheduling
/// only; the WAL state transitions + persistence live in [LocalWalSyncImpl].
class SyncReconciler {
  SyncReconciler._();
  static final SyncReconciler instance = SyncReconciler._();

  LocalWalSyncImpl? _phone;
  ConversationSurfaceCallback? _onConversations;

  Timer? _timer;
  bool _running = false;
  bool _foreground = true;
  int _idleStreak = 0;

  // Backoff while jobs are still processing server-side. Reset to fast cadence
  // whenever a pass makes progress (surfaces conversations / changes state).
  static const List<int> _backoffSecs = [20, 20, 30, 45, 60, 120];

  void attach(LocalWalSyncImpl phone, ConversationSurfaceCallback onConversations) {
    _phone = phone;
    _onConversations = onConversations;
  }

  /// Run one reconcile pass now. Wake coalescing belongs to
  /// [RecordingTransferCoordinator], so a caller never loses a recovery event
  /// because a previous pass is in flight.
  Future<void> poke() async {
    final phone = _phone;
    if (phone == null) return;
    if (_running) {
      throw StateError('SyncReconciler invoked outside RecordingTransferCoordinator');
    }
    _running = true;
    try {
      final resp = await phone.reconcileUploadedWals();
      final madeProgress = resp.newConversationIds.isNotEmpty || resp.updatedConversationIds.isNotEmpty;
      if (madeProgress) {
        _idleStreak = 0;
        try {
          await _onConversations?.call(resp);
        } catch (e) {
          Logger.debug('SyncReconciler: surface callback failed: $e');
        }
      }
    } catch (e) {
      Logger.debug('SyncReconciler: reconcile pass failed: $e');
      rethrow;
    } finally {
      _running = false;
    }
    await _reschedule();
  }

  Future<bool> _hasUploaded() async {
    final phone = _phone;
    if (phone == null) return false;
    final wals = await phone.getAllWals();
    return wals.any((w) => w.status == WalStatus.uploaded);
  }

  Future<void> _reschedule() async {
    _timer?.cancel();
    _timer = null;
    if (!_foreground) return;
    if (!await _hasUploaded()) {
      _idleStreak = 0;
      return; // nothing pending — go quiet until the next poke
    }
    final secs = _backoffSecs[_idleStreak.clamp(0, _backoffSecs.length - 1)];
    _idleStreak++;
    _timer = Timer(Duration(seconds: secs), () {
      unawaited(RecordingTransferCoordinator.instance.wake(WakeTrigger.cooldownElapsed));
    });
  }

  /// App came to the foreground — resume fast cadence and check immediately.
  void onForeground() {
    _foreground = true;
    _idleStreak = 0;
    RecordingTransferCoordinator.instance.setForeground(true);
    unawaited(RecordingTransferCoordinator.instance.wake(WakeTrigger.foregrounded));
  }

  /// App backgrounded — stop the timer. State is persisted; a later
  /// foreground/startup poke resumes. (No OS background execution by design.)
  void onBackground() {
    _foreground = false;
    _timer?.cancel();
    _timer = null;
    RecordingTransferCoordinator.instance.setForeground(false);
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }
}
