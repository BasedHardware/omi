import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart' show RateLimitReason;
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Pending audio at or above this reads as "catching up" on Home instead of a
/// count of conversations: a long backlog is normal after a day off the phone,
/// and an hour figure on Home reads as a problem.
const int largeSyncBacklogSeconds = 30 * 60;

/// The short reason a refused recording shows, shared by On the Way rows and
/// the Offline Sync pages. A server refusal names which refusal it was; a
/// refusal with no stored token (records refused before the token existed)
/// still reads as refused by the server rather than a bare "Failed".
String walAttentionLabel(WalSyncDisplayState state, AppLocalizations l, {String? rejectionReason}) => switch (state) {
      WalSyncDisplayState.corrupted => l.syncStatusFileUnavailable,
      WalSyncDisplayState.outsideRecoveryWindow => l.syncStatusTooOld,
      WalSyncDisplayState.unsupportedAudio => l.syncStatusUnsupportedAudio,
      WalSyncDisplayState.uploadRejected => switch (rejectionReason) {
          WalUploadRejection.invalidCaptureTime => l.syncRejectionInvalidDate,
          WalUploadRejection.tooLarge => l.syncRejectionTooLarge,
          _ => l.syncRejectionServer,
        },
      _ => l.syncStatusFailed,
    };

/// Recordings still on their way to becoming conversations, as Home's pending
/// row and the On the Way page read them from [SyncProvider].
///
/// Terminal recordings (retries exhausted, refused by the server) belong to the
/// Offline Sync page and never hold the row up on their own. Local-only
/// recordings (`onDeviceOnly`, on-device STT) never join a cloud drain, so they
/// would hold a row that can never clear.
abstract final class SyncPendingWork {
  static bool isForwardMoving(WalSyncDisplayState s) =>
      s == WalSyncDisplayState.waiting || s == WalSyncDisplayState.retrying || s == WalSyncDisplayState.syncing;

  /// Allocation-free on purpose: every SyncProvider notify rebuilds the row.
  static bool hasUploadedJobs(SyncProvider p) => p.allWals.any((w) => w.status == WalStatus.uploaded);

  static bool hasServerJobs(SyncProvider p) => hasUploadedJobs(p) || p.syncState.isProcessing;

  static bool isPendingWal(Wal w) =>
      w.status == WalStatus.miss && !w.onDeviceOnly && isForwardMoving(w.syncDisplayState);

  static bool shouldShow(SyncProvider p) => hasServerJobs(p) || p.allWals.any(isPendingWal);

  /// Ids of device recordings whose phone copy already moved on: lagging
  /// bookkeeping, not audio still on the device.
  static Set<String> hiddenDeviceTwinIds(List<Wal> wals) => wals
      .where((w) => !walIsOnDevice(w) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced))
      .map((w) => w.id)
      .toSet();

  /// Recordings uploaded and being transcribed on the server.
  static List<Wal> uploaded(SyncProvider p) =>
      p.displaySortedWals.where((w) => w.status == WalStatus.uploaded).toList(growable: false);

  /// Recordings still on the device or the phone, waiting for or in a sync.
  static List<Wal> syncing(SyncProvider p) => syncingOf(p.displaySortedWals);

  /// The rows [syncing] lists, from any ordering of the inventory: the device
  /// card reads the unsorted index and must show exactly what On the Way shows.
  static List<Wal> syncingOf(List<Wal> wals) {
    final hidden = hiddenDeviceTwinIds(wals);
    final pending =
        wals.where((w) => isPendingWal(w) && !(walIsOnDevice(w) && hidden.contains(w.id))).toList(growable: false);
    final sources = pending.where(walIsOnDevice).toList(growable: false);
    if (sources.isEmpty) return pending;
    // A device drain copies a recording to the phone piece by piece and keeps the source until the
    // final clear. The source already stands for the whole recording, so its copied pieces would
    // list the same audio twice.
    return pending.where((w) => !_isPieceOfSource(w, sources)).toList(growable: false);
  }

  static bool _isPieceOfSource(Wal w, List<Wal> sources) {
    if (walIsOnDevice(w) || w.originalStorage == null || w.originalStorage == WalStorage.disk) return false;
    for (final src in sources) {
      if (src.device != w.device) continue;
      final end = src.timerStart + (src.seconds > 0 ? src.seconds : 0);
      if (w.timerStart >= src.timerStart && w.timerStart <= end) return true;
    }
    return false;
  }

  static bool needsAttention(WalSyncDisplayState s) => isAttentionSyncState(s);

  /// Recordings the server refused or that ran out of retries; the Offline Sync page owns them.
  static List<Wal> attention(SyncProvider p) =>
      p.displaySortedWals.where((w) => needsAttention(w.syncDisplayState)).toList(growable: false);

  /// One pass over the unsorted index, stopping at the threshold: Home's row asks this on every
  /// SyncProvider notify, which streams progress during a sync.
  /// Per WAL list: SyncProvider replaces the list whenever a status changes (see its partition
  /// caches), and progress notifications reuse it, so a sync's ticks do not redo the scan.
  static final Expando<(int, bool)> _backlogMemo = Expando('largeSyncBacklog');

  static bool isLargeBacklog(SyncProvider p) {
    final wals = p.allWals;
    final memo = _backlogMemo[wals];
    if (memo != null && memo.$1 == wals.length) return memo.$2;
    final large = _computeLargeBacklog(p);
    _backlogMemo[wals] = (wals.length, large);
    return large;
  }

  static bool _computeLargeBacklog(SyncProvider p) {
    var seconds = 0;
    for (final w in p.allWals) {
      if (w.status != WalStatus.uploaded) continue;
      seconds += w.seconds > 0 ? w.seconds : 0;
      if (seconds >= largeSyncBacklogSeconds) return true;
    }
    // Same set On the Way lists: a device drain's copied pieces are not counted on top of their source.
    for (final w in syncing(p)) {
      seconds += w.seconds > 0 ? w.seconds : 0;
      if (seconds >= largeSyncBacklogSeconds) return true;
    }
    return false;
  }

  /// Where the pending work is right now, in one short line.
  static String stageLabel(SyncProvider p, AppLocalizations l) => stageLabelFor(
        p.syncState,
        l,
        rateLimited: p.isRateLimited,
        rateLimitReason: p.isRateLimited ? p.rateLimitReason : null,
        serverJobs: hasServerJobs(p),
      );

  /// [stageLabel] from its inputs, for a caller that already holds a memoized
  /// inventory snapshot and must not rescan the WAL list on every notify.
  static String stageLabelFor(
    SyncState s,
    AppLocalizations l, {
    required bool rateLimited,
    required RateLimitReason? rateLimitReason,
    required bool serverJobs,
  }) {
    final active = s.isSyncing && !s.isFetchingConversations;
    // Device downloads run through an upload cooldown (pulling audio uses no upload quota), so a
    // download in progress is reported as itself, not as the cooldown.
    if (active && s.phase == SyncPhase.downloadingFromDevice) return l.syncCardDownloadingTitle;
    if (rateLimited) return syncCooldownTitle(rateLimitReason, l);
    if (active) {
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          return l.syncCardDownloadingTitle;
        case SyncPhase.waitingForInternet:
          return l.syncCardWaitingInternet;
        case SyncPhase.uploadingToCloud:
          return l.syncCardUploadingTitle;
        case SyncPhase.idle:
        case SyncPhase.processingOnServer:
          break;
      }
    }
    if (serverJobs) return l.transcribing;
    return l.syncStatusWaiting;
  }
}

/// Opens the Offline Sync page the device settings open, behind the same gate:
/// work that lives on a storage-less pendant has no Offline Sync screen.
///
/// [phoneLocal] bypasses that gate for the Activity page's capture rows: a
/// phone-local problem (full phone disk, stalled phone upload) must reach the
/// page even when unrelated device recordings wait on a disconnected wearable.
/// The page still renders device rows read-only without the wearable, which is
/// exactly what a phone problem needs.
void openOfflineSyncDetails(BuildContext context, SyncProvider p, {bool? multiFileSync, bool phoneLocal = false}) {
  final hidden = SyncPendingWork.hiddenDeviceTwinIds(p.allWals);
  final hasDeviceWork = p.allWals.any((w) => w.status == WalStatus.miss && walIsOnDevice(w) && !hidden.contains(w.id));
  if (!phoneLocal && hasDeviceWork && !context.read<DeviceProvider>().isDeviceStorageSupport) {
    showOmiAlert(context, title: context.l10n.v2Undetected, message: context.l10n.v2UndetectedMessage);
    return;
  }
  final multi = multiFileSync ?? SharedPreferencesUtil().deviceSupportsMultiFileSync;
  routeToPage(context, multi ? const AutoSyncPage() : const SyncPage());
}
