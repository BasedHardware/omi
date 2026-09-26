import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/pages/conversations/widgets/device_storage_card.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/sync_card_progress_line.dart';
import 'package:omi/utils/sync_confirmation.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/pages/conversations/widgets/status_action_pill.dart';

/// The Manage Storage clear actions, each paired with the storage re-read.
///
/// The storage card renders the ring status this page read when it opened, so a
/// clear performed while the page stayed open left the card showing the
/// pre-clear numbers — the device still reported as full after its recordings
/// were gone. Pairing happens here, in one place, rather than in each handler:
/// the original defect was three independent handlers that each had to remember
/// the re-read, and none of which did.
///
/// The re-read has to follow the clear; taken first it would return exactly the
/// stale numbers being corrected. It also runs when the clear throws, because a
/// clear that failed part-way still deleted files and leaves the card just as
/// wrong; the failure itself still propagates to the caller.
({Future<void> Function() synced, Future<void> Function() pending, Future<void> Function() all})
    buildStorageClearActions({
  required Future<void> Function() clearSynced,
  required Future<void> Function() clearPending,
  required Future<void> Function() clearAll,
  required Future<void> Function() refreshDeviceStorage,
}) {
  Future<void> thenRefresh(Future<void> Function() clear) async {
    try {
      await clear();
    } finally {
      await refreshDeviceStorage();
    }
  }

  return (
    synced: () => thenRefresh(clearSynced),
    pending: () => thenRefresh(clearPending),
    all: () => thenRefresh(clearAll),
  );
}

class AutoSyncPage extends StatefulWidget {
  const AutoSyncPage({super.key});

  @override
  State<AutoSyncPage> createState() => _AutoSyncPageState();
}

class _AutoSyncPageState extends State<AutoSyncPage> {
  // Default to Pending instead of All. With thousands of synced recordings,
  // landing on All would force the whole list to mount up-front; landing on
  // Pending shows the small actionable set (or a calm empty state when the
  // user is up to date). All is still one tap away — and the list below is
  // sliver-lazy, so visiting it is safe even with thousands of items.
  WalDisplayFilter _filter = WalDisplayFilter.pending;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final syncProvider = context.read<SyncProvider>();
      final deviceProvider = context.read<DeviceProvider>();
      // Discover offline recordings straight from the device so they list here
      // even when auto-sync is off (device discovery otherwise only runs as the
      // first step of a full sync). Falls back to the cached list on failure.
      // Run BLE reads sequentially — this and the storage-usage read below both
      // hit the same device and would otherwise contend on the GATT link.
      await syncProvider.discoverDeviceWals(firmwareVersion: deviceProvider.currentFirmwareVersion);
      await deviceProvider.refreshRingStorageStatus();
      await RecordingTransferCoordinator.instance.wake(WakeTrigger.foregrounded);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<SyncProvider, UserProvider, DeviceProvider>(
      builder: (context, syncProvider, userProvider, deviceProvider, _) {
        final syncState = syncProvider.syncState;
        final hasAnyRecording = syncProvider.allWals.isNotEmpty;
        // Compute the filtered list once per build and pass it down — the
        // SliverList.builder uses it via index, so calling it again inside
        // itemBuilder would re-sort+re-filter on every visible row.
        final filteredWals = hasAnyRecording ? syncProvider.walsForDisplayFilter(_filter) : const <Wal>[];

        return Scaffold(
          // One name for the device-storage sync screen everywhere: "Offline Sync", as Settings calls it.
          appBar: OmiAppBar(
            leading: const OmiBackButton(),
            title: Text(context.l10n.offlineSync),
            actions: [
              OmiIconButton(
                icon: const FaIcon(FontAwesomeIcons.circleInfo, size: 18),
                label: context.l10n.howSyncingWorks,
                color: OmiColors.textSecondary,
                onPressed: () => _showInfoSheet(context),
              ),
              if (syncProvider.clearableWalsCount > 0)
                OmiIconButton(
                  icon: const FaIcon(FontAwesomeIcons.ellipsisVertical, size: 18),
                  label: context.l10n.manageStorage,
                  color: OmiColors.textSecondary,
                  onPressed: () => _showManageStorageSheet(context, syncProvider),
                ),
              const SizedBox(width: OmiSpacing.xxs),
            ],
          ),
          body: CustomScrollView(
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverList(
                  delegate: SliverChildListDelegate.fixed([
                    const SizedBox(height: 8),
                    _buildOverallStatusCard(syncProvider, syncState),
                    if (syncProvider.syncCompleted && syncProvider.syncedConversationsPointers.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      _buildConversationsCard(syncProvider),
                    ],
                    if (syncState.hasError) ...[const SizedBox(height: 16), _buildErrorCard(syncState, syncProvider)],
                    if (WalSyncs.isRingBufferFirmware(deviceProvider.currentFirmwareVersion) &&
                        deviceProvider.ringStatus != null) ...[
                      const SizedBox(height: 32),
                      DeviceStorageCard(status: deviceProvider.ringStatus!),
                    ],
                    // Canvas Sync: the recordings come straight after the status, Storage below them.
                    if (hasAnyRecording) ...[
                      const SizedBox(height: 22),
                      _buildFilterChips(),
                      const SizedBox(height: 12),
                    ],
                  ]),
                ),
              ),
              if (hasAnyRecording) _buildWalListSliver(syncProvider, filteredWals),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 32, 20, 48),
                sliver: SliverToBoxAdapter(child: _buildStorageSettings(userProvider, deviceProvider)),
              ),
            ],
          ),
        );
      },
    );
  }

  // ─────────────────────────────────────────
  // Overall status card
  // ─────────────────────────────────────────

  Widget _buildOverallStatusCard(SyncProvider p, SyncState s) {
    final l = context.l10n;
    final attention = p.needsAttentionWalsCount;
    final uploaded = p.uploadedWals.length;
    final readyToBackUp = p.displaySortedWals
        .where(
          (w) =>
              w.syncDisplayState == WalSyncDisplayState.waiting || w.syncDisplayState == WalSyncDisplayState.retrying,
        )
        .length;
    final hasAnyRecording = p.allWals.isNotEmpty;

    final isActive = s.isSyncing || s.isFetchingConversations;

    String title;
    String? progressText;
    Color titleColor = OmiColors.textPrimary;
    Widget? action;

    if (isActive) {
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          progressText = SyncCardProgressLine.subtitle(
            phase: s.phase,
            currentFile: s.currentFile,
            totalFiles: s.totalFiles,
            counterLabel: (processed, total) => l.syncCardProgressOf(processed, total),
          );
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          titleColor = OmiColors.warning;
          break;
        case SyncPhase.uploadingToCloud:
          title = l.syncCardUploadingTitle;
          progressText = SyncCardProgressLine.subtitle(
            phase: s.phase,
            currentFile: s.currentFile,
            totalFiles: s.totalFiles,
            counterLabel: (processed, total) => l.syncCardProgressOf(processed, total),
          );
          break;
        case SyncPhase.processingOnServer:
          title = l.syncCardProcessing;
          break;
        default:
          title = s.isFetchingConversations ? l.syncCardProcessing : l.syncCardUploadingTitle;
      }
      action = statusActionPill(l.cancel, OmiColors.danger, () => _confirmCancel(context, p));
    } else if (p.isRateLimited) {
      title = syncCooldownTitle(p.rateLimitReason, l);
      titleColor = OmiColors.warning;
    } else if (uploaded > 0) {
      // Uploads finished, reconciler is resolving jobs in the background.
      title = l.syncCardProcessing;
      final counts = p.offlineServerProcessingCounts;
      progressText = SyncCardProgressLine.serverProcessingSubtitle(
            processed: counts.processed,
            total: counts.total,
            counterLabel: (processed, total) => l.processingProgress(processed, total),
          ) ??
          l.syncProcessingBackgroundHint;
    } else if (attention > 0) {
      title = l.syncCardNeedsAttention(attention);
      titleColor = OmiColors.warning;
      action = statusActionPill(l.sync, OmiColors.accent, () async {
        if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
      });
    } else if (readyToBackUp > 0) {
      title = l.syncCardReadyCount(readyToBackUp);
      action = statusActionPill(l.sync, OmiColors.accent, () async {
        if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
      });
    } else if (hasAnyRecording) {
      title = l.syncCardAllBackedUp;
      titleColor = OmiColors.textSecondary;
    } else {
      // No recordings — same calm baseline; the card never pops in/out.
      title = l.syncCardAllBackedUp;
      titleColor = OmiColors.textSecondary;
    }

    // Canvas Sync: the device that holds the recordings, lit while they move, the state in large
    // type, and how far along the transfer is.
    final deviceName = context.read<DeviceProvider>().pairedDevice?.name.trim() ?? '';
    return OmiCard(
      key: const Key('sync_status_hero'),
      radius: OmiRadius.cardLarge,
      padding: const EdgeInsets.all(18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          OmiOrb(size: 64, live: isActive),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (deviceName.isNotEmpty) ...[
                  Text(
                    deviceName,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                ],
                Text(
                  title,
                  style: OmiType.title3.copyWith(color: titleColor, fontWeight: FontWeight.w700),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (progressText != null) ...[
                  const SizedBox(height: 4),
                  Text(progressText, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ],
                if (isActive && s.progress > 0) ...[
                  const SizedBox(height: 10),
                  OmiProgressBar(value: s.progress),
                ],
                if (action != null) ...[const SizedBox(height: OmiSpacing.sm), action],
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────
  // Conversations created
  // ─────────────────────────────────────────

  Widget _buildConversationsCard(SyncProvider syncProvider) {
    final count = syncProvider.syncedConversationsPointers.length;
    return GestureDetector(
      onTap: () => routeToPage(context, const SyncedConversationsPage()),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: BorderRadius.circular(20)),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.success.withValues(alpha: 0.15), shape: BoxShape.circle),
              child: Center(child: FaIcon(FontAwesomeIcons.check, color: OmiColors.success, size: 14)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                context.l10n.nConversationsCreated(count),
                style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w500),
              ),
            ),
            FaIcon(FontAwesomeIcons.chevronRight, color: OmiColors.textTertiary, size: 12),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────
  //  Error card
  // ─────────────────────────────────────────

  Widget _buildErrorCard(SyncState syncState, SyncProvider syncProvider) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: OmiColors.danger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: OmiColors.danger.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          FaIcon(FontAwesomeIcons.circleExclamation, color: OmiColors.danger, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              SyncProvider.isPendingUploadError(syncState.errorMessage)
                  ? context.l10n.syncStatusFailed
                  : syncState.errorMessage ?? context.l10n.syncFailed,
              style: TextStyle(color: OmiColors.danger, fontSize: 13),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () => syncProvider.retrySync(),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: OmiColors.danger.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                context.l10n.retry,
                style: TextStyle(color: OmiColors.danger, fontSize: 13, fontWeight: FontWeight.w500),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────
  // Storage settings
  // ─────────────────────────────────────────

  /// Canvas Sync "Storage": syncing on connect, then where audio is kept (each opens its page).
  Widget _buildStorageSettings(UserProvider userProvider, DeviceProvider deviceProvider) {
    final l10n = context.l10n;
    final isPhoneOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final isCloudOn = userProvider.privateCloudSyncEnabled;
    return OmiSettingsGroup(
      header: l10n.storageTitle,
      children: [
        // Omi devices only, as on the device page.
        if (deviceProvider.pairedDevice?.type == DeviceType.omi)
          OmiSettingsRow.toggle(
            key: const Key('sync_auto_toggle'),
            leading: const FaIcon(FontAwesomeIcons.arrowsRotate),
            title: l10n.autoSync,
            subtitle: l10n.autoSyncDescription,
            value: SharedPreferencesUtil().autoSyncOfflineRecordings,
            onChanged: (value) => setState(() => SharedPreferencesUtil().autoSyncOfflineRecordings = value),
          ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.mobile),
          title: l10n.storeAudioOnPhone,
          value: isPhoneOn ? l10n.on : l10n.off,
          showChevron: true,
          onTap: () => routeToPage(context, const LocalStoragePage()).then((_) => setState(() {})),
        ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.cloud),
          title: l10n.storeAudioOnCloud,
          value: isCloudOn ? l10n.on : l10n.off,
          showChevron: true,
          onTap: () => routeToPage(context, const PrivateCloudSyncPage()),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────
  // Filter chips + WAL list
  // ─────────────────────────────────────────

  /// Canvas Sync: Pending / Synced / All as the shared segmented control.
  Widget _buildFilterChips() {
    return OmiSegmentedControl<WalDisplayFilter>(
      segments: [
        OmiSegment(value: WalDisplayFilter.pending, label: context.l10n.pending),
        OmiSegment(value: WalDisplayFilter.synced, label: context.l10n.synced),
        OmiSegment(value: WalDisplayFilter.all, label: context.l10n.all),
      ],
      selected: _filter,
      onChanged: (f) => setState(() => _filter = f),
    );
  }

  /// Sliver-based wal list. SliverList.builder mounts only the rows currently
  /// near the viewport, so navigating to a filter with thousands of items no
  /// longer instantiates thousands of Dismissibles in one frame.
  ///
  /// The visual "rounded card" wrapper is achieved per-row: the first item gets
  /// rounded top corners, the last gets rounded bottom corners. Dividers are
  /// drawn between rows. This preserves the design while staying lazy.
  Widget _buildWalListSliver(SyncProvider syncProvider, List<Wal> wals) {
    if (wals.isEmpty) {
      final emptyMsg = switch (_filter) {
        WalDisplayFilter.synced => context.l10n.noSyncedRecordingsYet,
        WalDisplayFilter.pending => context.l10n.noPendingRecordings,
        _ => context.l10n.noRecordingsYet,
      };
      return SliverPadding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        sliver: SliverToBoxAdapter(
          child: OmiCard(
            padding: const EdgeInsets.all(32),
            child: Center(
              child: Text(emptyMsg, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
            ),
          ),
        ),
      );
    }

    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      sliver: SliverList.builder(
        itemCount: wals.length,
        itemBuilder: (context, i) => _buildWalListItem(syncProvider, wals, i),
      ),
    );
  }

  Widget _buildWalListItem(SyncProvider syncProvider, List<Wal> wals, int i) {
    final wal = wals[i];
    final state = wal.syncDisplayState;
    final isFirst = i == 0;
    final isLast = i == wals.length - 1;
    // Canvas Sync: the recordings share one card (rounded at its ends), a hairline between rows.
    return Container(
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: BorderRadius.vertical(
          top: isFirst ? const Radius.circular(OmiRadius.card) : Radius.zero,
          bottom: isLast ? const Radius.circular(OmiRadius.card) : Radius.zero,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Dismissible(
            // Index suffix because `wal.id` (device_timerStart) is not unique
            // across SD-card + on-phone copies of the same recording.
            key: ValueKey('${wal.id}#$i'),
            direction: state == WalSyncDisplayState.syncing ? DismissDirection.none : DismissDirection.endToStart,
            confirmDismiss: (direction) {
              final uploading = wal.syncDisplayState == WalSyncDisplayState.uploaded;
              return showOmiConfirm(
                context,
                title: uploading ? context.l10n.deleteWhileProcessingTitle : context.l10n.deleteRecording,
                message: uploading ? context.l10n.deleteWhileProcessingMessage : context.l10n.thisCannotBeUndone,
                confirmLabel: context.l10n.delete,
                destructive: true,
              );
            },
            background: Container(
              alignment: Alignment.centerRight,
              padding: const EdgeInsets.only(right: 20.0),
              color: OmiColors.danger,
              child: const Icon(Icons.delete_outline_rounded, color: Colors.white),
            ),
            onDismissed: (direction) {
              syncProvider.deleteWal(wal);
            },
            child: _walRow(wal),
          ),
          if (!isLast) Divider(height: 0.5, thickness: 0.5, color: OmiColors.border, indent: 64),
        ],
      ),
    );
  }

  Widget _walRow(Wal wal) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final timeStr = dates.time(date);
    final dateStr = dates.dayHeader(date);
    final duration = wal.seconds > 0 ? OmiDuration.compact(wal.seconds, context.l10n) : null;

    final state = wal.syncDisplayState;
    var (color, _, label) = _rowVisual(state);
    final isSynced = state == WalSyncDisplayState.synced;

    // On-device WALs surface their transfer state instead of "Waiting to sync".
    final onDevice = wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;
    if (state == WalSyncDisplayState.waiting && onDevice) {
      final phase = context.read<SyncProvider>().syncState.phase;
      label = phase == SyncPhase.downloadingFromDevice
          ? context.l10n.syncStatusDownloadingFromDevice
          : context.l10n.syncStatusOnDevice;
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        final syncProvider = context.read<SyncProvider>();
        if (syncProvider.isSyncing && wal.storage == WalStorage.sdcard) {
          OmiFeedback.info(context, context.l10n.syncInProgress);
          return;
        }
        routeToPage(context, WalItemDetailPage(wal: wal));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            // Canvas Sync: each recording is a waveform tile, its day, time and length, then its state.
            const OmiIconTile(size: 36, child: OmiGlyph(OmiGlyphs.waveform, size: 20)),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$dateStr \u00b7 $timeStr${duration != null ? ' \u00b7 $duration' : ''}',
                    style: OmiType.body.copyWith(
                      color: isSynced ? OmiColors.textTertiary : OmiColors.textPrimary,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(color: color),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            _rowTrailing(wal, state),
          ],
        ),
      ),
    );
  }

  Widget _rowTrailing(Wal wal, WalSyncDisplayState state) {
    if (state == WalSyncDisplayState.syncing) {
      return const OmiSpinner(size: OmiSpinnerSize.small);
    }
    if (state == WalSyncDisplayState.failed || state == WalSyncDisplayState.retrying) {
      return OmiButton.secondary(
        label: context.l10n.tryAgain,
        size: OmiButtonSize.compact,
        onPressed: () => context.read<SyncProvider>().syncWal(wal),
      );
    }
    // Nothing can move these forward, so the only honest action is removal.
    // Swipe-to-delete already works, but it is invisible: without a labelled
    // control the needs-attention banner reads as permanent chores.
    if (_isUnsyncableState(state)) {
      return OmiButton.destructive(
        label: context.l10n.delete,
        size: OmiButtonSize.compact,
        onPressed: () => _confirmDeleteWal(wal),
      );
    }
    return FaIcon(FontAwesomeIcons.chevronRight, color: OmiColors.textTertiary, size: 12);
  }

  /// Terminal states no upload can resolve. [WalSyncDisplayState.failed] is
  /// deliberately absent: its retry budget is spent but a deliberate retry can
  /// still succeed, so that row keeps its Retry.
  static bool _isUnsyncableState(WalSyncDisplayState state) =>
      state == WalSyncDisplayState.corrupted ||
      state == WalSyncDisplayState.outsideRecoveryWindow ||
      state == WalSyncDisplayState.unsupportedAudio;

  Future<void> _confirmDeleteWal(Wal wal) async {
    final syncProvider = context.read<SyncProvider>();
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.thisCannotBeUndone,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (confirmed) await syncProvider.deleteWal(wal);
  }

  /// Row subtitle (color, icon, label). Colors stay restrained: grey for
  /// neutral/active, amber for auto-retry, red for failed/corrupted. Purple
  /// is reserved for actions and the spinner — not body text.
  (Color, FaIconData, String) _rowVisual(WalSyncDisplayState state) {
    switch (state) {
      case WalSyncDisplayState.synced:
        return (OmiColors.textTertiary, FontAwesomeIcons.cloudArrowUp, context.l10n.syncStatusConversationCreated);
      case WalSyncDisplayState.syncing:
        return (OmiColors.textSecondary, FontAwesomeIcons.arrowsRotate, context.l10n.syncStatusBackingUp);
      case WalSyncDisplayState.uploaded:
        return (OmiColors.textSecondary, FontAwesomeIcons.cloud, context.l10n.syncStatusUploaded);
      case WalSyncDisplayState.waiting:
        return (OmiColors.textTertiary, FontAwesomeIcons.cloudArrowUp, context.l10n.syncStatusWaiting);
      case WalSyncDisplayState.retrying:
        return (OmiColors.warning, FontAwesomeIcons.arrowsRotate, context.l10n.syncStatusRetrying);
      case WalSyncDisplayState.failed:
        return (OmiColors.danger, FontAwesomeIcons.circleExclamation, context.l10n.syncStatusFailed);
      case WalSyncDisplayState.corrupted:
        return (OmiColors.danger, FontAwesomeIcons.triangleExclamation, context.l10n.syncStatusFileUnavailable);
      case WalSyncDisplayState.outsideRecoveryWindow:
        return (OmiColors.danger, FontAwesomeIcons.clockRotateLeft, context.l10n.syncStatusTooOld);
      case WalSyncDisplayState.unsupportedAudio:
        return (OmiColors.danger, FontAwesomeIcons.fileCircleExclamation, context.l10n.syncStatusUnsupportedAudio);
    }
  }

  // ─────────────────────────────────────────
  // Info bottom sheet
  // ─────────────────────────────────────────

  void _showInfoSheet(BuildContext context) {
    final l = context.l10n;
    showOmiSheet<void>(
      context: context,
      title: l.howSyncingWorks,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xxs, OmiSpacing.xl, OmiSpacing.xl),
      builder: (context) {
        return SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l.syncFlowIntro, style: TextStyle(color: OmiColors.textSecondary, fontSize: 14, height: 1.45)),
              const SizedBox(height: 22),
              _syncFlowStep(1, l.syncStepUpload, l.syncStepUploadDesc),
              const SizedBox(height: 16),
              _syncFlowStep(2, l.syncStepProcess, l.syncStepProcessDesc),
              const SizedBox(height: 16),
              _syncFlowStep(3, l.syncStepBackedUp, l.syncStepBackedUpDesc),
              const SizedBox(height: 22),
              Text(l.syncFailureFootnote, style: TextStyle(color: OmiColors.textTertiary, fontSize: 13, height: 1.45)),
            ],
          ),
        );
      },
    );
  }

  Widget _syncFlowStep(int n, String title, String desc) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 22,
          child: Text(
            '$n.',
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 3),
              Text(desc, style: TextStyle(color: OmiColors.textSecondary, fontSize: 13, height: 1.45)),
            ],
          ),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────
  // Manage storage
  // ─────────────────────────────────────────

  void _showManageStorageSheet(BuildContext context, SyncProvider provider) {
    // Built before the sheet's async callbacks run, so the clear handlers do not
    // reach through a BuildContext across an await — and so every action is
    // paired with the storage re-read at a single construction site.
    final clearActions = buildStorageClearActions(
      clearSynced: provider.deleteAllSyncedWals,
      clearPending: provider.deleteAllPendingWals,
      clearAll: provider.deleteAllClearableWals,
      refreshDeviceStorage: context.read<DeviceProvider>().refreshRingStorageStatus,
    );
    showOmiSheet<void>(
      context: context,
      title: context.l10n.manageStorage,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xl),
      builder: (sheetContext) => _ManageStorageSheet(
        provider: provider,
        onClearSynced: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deleteSyncedFiles,
            message: context.l10n.deleteSyncedFilesMessage,
            confirmLabel: context.l10n.clear,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await clearActions.synced();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.syncedFilesDeleted);
            }
          }
        },
        onClearPending: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deletePendingFiles,
            message: context.l10n.deletePendingFilesWarning,
            confirmLabel: context.l10n.clear,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await clearActions.pending();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.pendingFilesDeleted);
            }
          }
        },
        onClearAll: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await showOmiConfirm(
            context,
            title: context.l10n.deleteAllFiles,
            message: context.l10n.deleteAllFilesWarning,
            confirmLabel: context.l10n.clearAll,
            destructive: true,
          );
          if (confirmed && context.mounted) {
            await clearActions.all();
            if (context.mounted) {
              OmiFeedback.confirm(context, context.l10n.allFilesDeleted);
            }
          }
        },
      ),
    );
  }

  // ─────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────

  void _confirmCancel(BuildContext context, SyncProvider syncProvider) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.cancelSyncQuestion,
      message: context.l10n.filesDownloadedUploadedNextTime,
      confirmLabel: context.l10n.cancelSync,
      cancelLabel: context.l10n.keepSyncing,
      destructive: true,
    );
    if (confirmed) {
      syncProvider.cancelSync();
    }
  }
}

class _ManageStorageSheet extends StatelessWidget {
  final SyncProvider provider;
  final VoidCallback onClearSynced;
  final VoidCallback onClearPending;
  final VoidCallback onClearAll;

  const _ManageStorageSheet({
    required this.provider,
    required this.onClearSynced,
    required this.onClearPending,
    required this.onClearAll,
  });

  @override
  Widget build(BuildContext context) {
    final syncedCount = provider.syncedWals.length;
    final pendingCount = provider.pendingDeletableWals.length;
    final totalCount = provider.clearableWalsCount;

    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _StorageRow(
            icon: FontAwesomeIcons.circleCheck,
            iconColor: OmiColors.success,
            title: context.l10n.synced,
            subtitle: context.l10n.safelyBackedUp,
            count: syncedCount,
            onClear: syncedCount > 0 ? onClearSynced : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: 12),
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            iconColor: OmiColors.warning,
            title: context.l10n.pending,
            subtitle: context.l10n.notYetSynced,
            count: pendingCount,
            onClear: pendingCount > 0 ? onClearPending : null,
            clearLabel: context.l10n.clear,
            isWarning: true,
          ),
          if (totalCount > 0) ...[
            const SizedBox(height: 20),
            OmiButton.destructive(label: context.l10n.clearAll, expand: true, onPressed: onClearAll),
          ],
        ],
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  final FaIconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final int count;
  final VoidCallback? onClear;
  final String clearLabel;
  final bool isWarning;

  const _StorageRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
    this.isWarning = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(child: FaIcon(icon, size: 16, color: iconColor)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: TextStyle(color: OmiColors.textPrimary, fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: OmiColors.textPrimary.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text('$count', style: TextStyle(color: OmiColors.textSecondary, fontSize: 12)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(subtitle, style: TextStyle(color: OmiColors.textTertiary, fontSize: 12)),
              ],
            ),
          ),
          if (onClear != null)
            GestureDetector(
              onTap: onClear,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: (isWarning ? OmiColors.warning : OmiColors.danger).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(
                  clearLabel,
                  style: TextStyle(
                    color: isWarning ? OmiColors.warning : OmiColors.danger,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
