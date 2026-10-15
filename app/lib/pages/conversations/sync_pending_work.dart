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
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// Pending audio at or above this reads as "catching up" on Home instead of a
/// count of conversations: a long backlog is normal after a day off the phone,
/// and an hour figure on Home reads as a problem.
const int largeSyncBacklogSeconds = 30 * 60;

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
  static Set<String> movedIds(SyncProvider p) => p.allWals
      .where((w) => !walIsOnDevice(w) && (w.status == WalStatus.uploaded || w.status == WalStatus.synced))
      .map((w) => w.id)
      .toSet();

  /// Recordings uploaded and being transcribed on the server.
  static List<Wal> uploaded(SyncProvider p) =>
      p.displaySortedWals.where((w) => w.status == WalStatus.uploaded).toList(growable: false);

  /// Recordings still on the device or the phone, waiting for or in a sync.
  static List<Wal> syncing(SyncProvider p) {
    final moved = movedIds(p);
    return p.displaySortedWals
        .where((w) => isPendingWal(w) && !(walIsOnDevice(w) && moved.contains(w.id)))
        .toList(growable: false);
  }

  static bool needsAttention(WalSyncDisplayState s) =>
      s == WalSyncDisplayState.failed ||
      s == WalSyncDisplayState.corrupted ||
      s == WalSyncDisplayState.outsideRecoveryWindow ||
      s == WalSyncDisplayState.unsupportedAudio ||
      s == WalSyncDisplayState.uploadRejected;

  /// Recordings the server refused or that ran out of retries; the Offline Sync page owns them.
  static List<Wal> attention(SyncProvider p) =>
      p.displaySortedWals.where((w) => needsAttention(w.syncDisplayState)).toList(growable: false);

  static int pendingSeconds(SyncProvider p) => walSeconds(uploaded(p)) + walSeconds(syncing(p));

  static bool isLargeBacklog(SyncProvider p) => pendingSeconds(p) >= largeSyncBacklogSeconds;

  /// Where the pending work is right now, in one short line.
  static String stageLabel(SyncProvider p, AppLocalizations l) {
    if (p.isRateLimited) return syncCooldownTitle(p.rateLimitReason, l);
    final s = p.syncState;
    if (s.isSyncing && !s.isFetchingConversations) {
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
    if (hasServerJobs(p)) return l.transcribing;
    return l.syncStatusWaiting;
  }
}

/// Opens the Offline Sync page the device settings open, behind the same gate:
/// work that lives on a storage-less pendant has no Offline Sync screen.
void openOfflineSyncDetails(BuildContext context, SyncProvider p, {bool? multiFileSync}) {
  final moved = SyncPendingWork.movedIds(p);
  final hasDeviceWork = p.allWals.any((w) => w.status == WalStatus.miss && walIsOnDevice(w) && !moved.contains(w.id));
  if (hasDeviceWork && !context.read<DeviceProvider>().isDeviceStorageSupport) {
    showOmiAlert(context, title: context.l10n.v2Undetected, message: context.l10n.v2UndetectedMessage);
    return;
  }
  final multi = multiFileSync ?? SharedPreferencesUtil().deviceSupportsMultiFileSync;
  routeToPage(context, multi ? const AutoSyncPage() : const SyncPage());
}
