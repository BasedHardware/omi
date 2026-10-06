import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/pages/conversations/widgets/device_download_meter.dart';
import 'package:omi/pages/conversations/widgets/device_storage_card.dart';
import 'package:omi/pages/conversations/widgets/sync_error_card.dart';
import 'package:omi/pages/conversations/widgets/sync_list_header.dart';
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

        return OmiGroupedPage(
          // One name for the device-storage sync screen everywhere: "Offline Sync", as Settings calls it.
          title: context.l10n.offlineSync,
          actions: [
            OmiIconButton.filled(
              icon: const OmiLineIcon(OmiLineGlyph.info, size: 20),
              label: context.l10n.howSyncingWorks,
              onPressed: () => _showInfoSheet(context),
            ),
            if (syncProvider.clearableWalsCount > 0)
              OmiIconButton.filled(
                icon: const OmiLineIcon(OmiLineGlyph.more, size: 20),
                label: context.l10n.manageStorage,
                onPressed: () => _showManageStorageSheet(context, syncProvider),
              ),
          ],
          body: CustomScrollView(
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
                sliver: SliverList(
                  delegate: SliverChildListDelegate.fixed([
                    _buildOverallStatusCard(syncProvider, syncState),
                    if (syncProvider.syncCompleted && syncProvider.syncedConversationsPointers.isNotEmpty) ...[
                      const SizedBox(height: OmiSpacing.sm),
                      _buildConversationsCard(syncProvider),
                    ],
                    if (syncState.hasError) ...[
                      const SizedBox(height: OmiSpacing.sm),
                      _buildErrorCard(syncState, syncProvider),
                    ],
                    if (WalSyncs.isRingBufferFirmware(deviceProvider.currentFirmwareVersion) &&
                        deviceProvider.ringStatus != null) ...[
                      const SizedBox(height: OmiSpacing.xl),
                      DeviceStorageCard(status: deviceProvider.ringStatus!),
                    ],
                    const SizedBox(height: OmiSpacing.xl),
                    _buildStorageSettings(userProvider),
                    if (hasAnyRecording) ...[
                      const SizedBox(height: OmiSpacing.xl),
                      _buildRecordingsHeader(filteredWals.length),
                      _buildFilterChips(),
                      const SizedBox(height: OmiSpacing.sm),
                    ],
                  ]),
                ),
              ),
              if (hasAnyRecording) _buildWalListSliver(syncProvider, filteredWals),
              const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.xxl)),
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

    final isActive = s.isSyncing || s.isFetchingConversations;
    final bool showSpinner = (isActive || uploaded > 0) && !p.isRateLimited;

    String title;
    String? progressText;
    // Black and white like the rest of Settings; amber only when something is held up.
    var warning = false;
    var icon = FontAwesomeIcons.circleCheck;
    Widget? action;

    Widget syncAction() => OmiButton(
          label: l.sync,
          size: OmiButtonSize.compact,
          onPressed: () async {
            if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
          },
        );

    if (isActive) {
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          // Percent and speed live on [DeviceDownloadMeter], not the file-count line.
          // A ring download has no file index, so the old subtitle stayed blank.
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          warning = true;
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
      action = OmiButton.secondary(
        label: l.cancel,
        size: OmiButtonSize.compact,
        onPressed: () => _confirmCancel(context, p),
      );
    } else if (p.isRateLimited) {
      title = syncCooldownTitle(p.rateLimitReason, l);
      warning = true;
      icon = FontAwesomeIcons.clock;
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
      warning = true;
      icon = FontAwesomeIcons.circleExclamation;
      action = syncAction();
    } else if (readyToBackUp > 0) {
      title = l.syncCardReadyCount(readyToBackUp);
      icon = FontAwesomeIcons.cloudArrowUp;
      action = syncAction();
    } else {
      // All backed up, or no recordings yet: the same calm baseline, so the card never pops in/out.
      title = l.syncCardAllBackedUp;
    }

    final downloading = isActive && s.phase == SyncPhase.downloadingFromDevice;

    return OmiGroupedCard(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              OmiSettingsIconTile(
                showSpinner
                    ? const OmiSpinner(size: OmiSpinnerSize.small)
                    : FaIcon(icon, color: warning ? OmiColors.warning : null),
              ),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: OmiType.body.copyWith(color: warning ? OmiColors.warning : OmiColors.textPrimary),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (progressText != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        progressText,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      ),
                    ],
                  ],
                ),
              ),
              if (action != null) ...[const SizedBox(width: OmiSpacing.sm), action],
            ],
          ),
          // Main's meter while the pendant's files come down, under the status.
          if (downloading) ...[
            const SizedBox(height: OmiSpacing.sm),
            DeviceDownloadMeter(fraction: s.progress, speedKBps: s.speedKBps),
          ],
        ],
      ),
    );
  }

  // ─────────────────────────────────────────
  // Conversations created
  // ─────────────────────────────────────────

  Widget _buildConversationsCard(SyncProvider syncProvider) {
    return OmiSettingsGroup(
      children: [
        OmiSettingsRow(
          leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.check)),
          title: context.l10n.nConversationsCreated(syncProvider.syncedConversationsPointers.length),
          onTap: () => routeToPage(context, const SyncedConversationsPage()),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────
  //  Error card
  // ─────────────────────────────────────────

  Widget _buildErrorCard(SyncState syncState, SyncProvider syncProvider) {
    return SyncErrorCard(
      message: SyncProvider.isPendingUploadError(syncState.errorMessage)
          ? context.l10n.syncStatusFailed
          : syncState.errorMessage ?? context.l10n.syncFailed,
      onRetry: () => syncProvider.retrySync(),
    );
  }

  // ─────────────────────────────────────────
  // Storage settings
  // ─────────────────────────────────────────

  Widget _buildStorageSettings(UserProvider userProvider) {
    final l = context.l10n;
    final isPhoneOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final isCloudOn = userProvider.privateCloudSyncEnabled;
    final autoRemoveOn = SharedPreferencesUtil().autoRemoveSyncedCopies;
    final autoRemoveDays = SharedPreferencesUtil().autoRemoveSyncedCopiesDays;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsGroup(
          header: l.storageSection,
          children: [
            OmiSettingsRow(
              leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.mobile)),
              title: l.storeAudioOnPhone,
              value: isPhoneOn ? l.on : l.off,
              showChevron: true,
              onTap: () => routeToPage(context, const LocalStoragePage()).then((_) => setState(() {})),
            ),
            OmiSettingsRow(
              leading: const OmiSettingsIconTile(FaIcon(FontAwesomeIcons.cloud)),
              title: l.storeAudioOnCloud,
              value: isCloudOn ? l.on : l.off,
              showChevron: true,
              onTap: () => routeToPage(context, const PrivateCloudSyncPage()),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          header: l.localCopiesSection,
          children: [
            OmiSettingsRow.toggle(
              leading: const OmiSettingsIconTile(Icon(Icons.auto_delete)),
              title: l.autoRemoveSyncedCopiesTitle,
              subtitle: l.autoRemoveSyncedCopiesDescription(autoRemoveDays),
              value: autoRemoveOn,
              onChanged: (value) async {
                SharedPreferencesUtil().autoRemoveSyncedCopies = value;
                if (value) {
                  // Apply immediately: expired copies should not wait for the
                  // next sync pass or app restart.
                  await context.read<SyncProvider>().applySyncedCopyRetention();
                }
                if (context.mounted) setState(() {});
              },
            ),
          ],
        ),
      ],
    );
  }

  // ─────────────────────────────────────────
  // Filter + WAL list
  // ─────────────────────────────────────────

  /// The small label over the list, like every other section on the page: "Recordings 12" and the
  /// sort order. The count is the filtered list's; an empty filter says so in the card below.
  Widget _buildRecordingsHeader(int total) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
      child: Row(
        children: [
          Semantics(
            header: true,
            child: Text(
              context.l10n.recordings,
              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textSecondary),
            ),
          ),
          if (total > 0) ...[
            const SizedBox(width: OmiSpacing.xs),
            Text('$total', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          ],
          const Spacer(),
          Text(context.l10n.newestFirst, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
        ],
      ),
    );
  }

  Widget _buildFilterChips() {
    return OmiSegmentedControl<WalDisplayFilter>(
      value: _filter,
      segments: {
        WalDisplayFilter.all: context.l10n.all,
        WalDisplayFilter.pending: context.l10n.pending,
        WalDisplayFilter.synced: context.l10n.synced,
      },
      onChanged: (filter) => setState(() => _filter = filter),
    );
  }

  /// Sliver-based wal list. SliverList.builder mounts only the rows currently
  /// near the viewport, so navigating to a filter with thousands of items no
  /// longer instantiates thousands of Dismissibles in one frame. Recordings are
  /// grouped by day under a small label, each day one outlined card drawn row by
  /// row ([OmiGroupedSlice]), so the list stays lazy and a row only needs the time.
  Widget _buildWalListSliver(SyncProvider syncProvider, List<Wal> wals) {
    if (wals.isEmpty) {
      final emptyMsg = switch (_filter) {
        WalDisplayFilter.synced => context.l10n.noSyncedRecordingsYet,
        WalDisplayFilter.pending => context.l10n.noPendingRecordings,
        _ => context.l10n.noRecordingsYet,
      };
      return SliverPadding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
        sliver: SliverToBoxAdapter(
          child: OmiGroupedCard(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xl),
            child: Text(
              emptyMsg,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
            ),
          ),
        ),
      );
    }

    // One pass, in the list's own order (newest first): a day label before each day's first row.
    final items = <Object>[];
    DateTime? day;
    for (var i = 0; i < wals.length; i++) {
      final at = DateTime.fromMillisecondsSinceEpoch(wals[i].timerStart * 1000).toLocal();
      final thisDay = DateTime(at.year, at.month, at.day);
      if (thisDay != day) {
        items.add(thisDay);
        day = thisDay;
      }
      items.add(i);
    }

    return SliverList.builder(
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        if (item is DateTime) {
          return SyncListHeader(label: OmiDateFormat.of(context).dayHeader(item), first: index == 0);
        }
        final i = item as int;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          child: OmiGroupedSlice(
            first: items[index - 1] is DateTime,
            last: index + 1 >= items.length || items[index + 1] is DateTime,
            child: _buildWalListItem(syncProvider, wals, i),
          ),
        );
      },
    );
  }

  Widget _buildWalListItem(SyncProvider syncProvider, List<Wal> wals, int i) {
    final wal = wals[i];
    final state = wal.syncDisplayState;
    return Dismissible(
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
        padding: const EdgeInsets.only(right: OmiSpacing.lg),
        color: OmiColors.danger,
        child: OmiLineIcon(OmiLineGlyph.trash, size: 22, color: OmiColors.onAccent),
      ),
      onDismissed: (direction) {
        syncProvider.deleteWal(wal);
      },
      child: _walRow(wal),
    );
  }

  /// Bar fraction for the recording that is actually leaving the device.
  /// Phone-local "Waiting to sync" rows stay null so they do not grow a bar.
  /// Percent and speed are not returned here; those stay on the status card.
  double? _rowDownloadFraction(Wal wal) {
    final sync = context.read<SyncProvider>();
    if (!sync.syncState.isSyncing || sync.syncState.phase != SyncPhase.downloadingFromDevice) return null;
    final onDevice = wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;
    if (!onDevice || wal.status != WalStatus.miss) return null;
    if (wal.deviceDownloadFraction != null) return wal.deviceDownloadFraction;
    if (wal.isSyncing) return sync.syncState.progress;
    if (wal.syncDisplayState != WalSyncDisplayState.waiting) return null;
    final peers = sync.allWals.where(
      (w) => (w.storage == WalStorage.sdcard || w.storage == WalStorage.flashPage) && w.status == WalStatus.miss,
    );
    if (peers.length == 1 && peers.first.id == wal.id) return sync.syncState.progress;
    return null;
  }

  Widget _walRow(Wal wal) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final timeStr = dates.time(date);
    final duration = wal.seconds > 0 ? OmiDuration.compact(wal.seconds, context.l10n) : null;

    final state = wal.syncDisplayState;
    var (color, label) = _rowVisual(state);
    final isSynced = state == WalSyncDisplayState.synced;

    // On-device WALs surface their transfer state instead of "Waiting to sync".
    final onDevice = wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;
    if (state == WalSyncDisplayState.waiting && onDevice) {
      final phase = context.read<SyncProvider>().syncState.phase;
      label = phase == SyncPhase.downloadingFromDevice
          ? context.l10n.syncStatusDownloadingFromDevice
          : context.l10n.syncStatusOnDevice;
    }

    final fraction = _rowDownloadFraction(wal);
    final row = OmiSettingsRow(
      // The day is the label above; the row only needs the time.
      title: '$timeStr${duration != null ? ' · $duration' : ''}',
      // Backed-up recordings step back; the ones still to sync read first.
      titleStyle: isSynced ? OmiType.body.copyWith(color: OmiColors.textSecondary) : null,
      subtitle: label,
      subtitleColor: color,
      trailing: _rowTrailing(wal, state),
      onTap: () {
        final syncProvider = context.read<SyncProvider>();
        if (syncProvider.isSyncing && wal.storage == WalStorage.sdcard) {
          OmiFeedback.info(context, context.l10n.syncInProgress);
          return;
        }
        routeToPage(context, WalItemDetailPage(wal: wal));
      },
    );
    if (fraction == null) return row;
    // While this recording comes down from the device, a slim meter under its text.
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        row,
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.sm),
          child: DeviceDownloadMeter(fraction: fraction, showReadout: false, barHeight: 4),
        ),
      ],
    );
  }

  /// The row's one control; null leaves the row's chevron.
  Widget? _rowTrailing(Wal wal, WalSyncDisplayState state) {
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
    return null;
  }

  /// Terminal states no upload can resolve. [WalSyncDisplayState.failed] is
  /// deliberately absent: its retry budget is spent but a deliberate retry can
  /// still succeed, so that row keeps its Retry.
  static bool _isUnsyncableState(WalSyncDisplayState state) =>
      state == WalSyncDisplayState.corrupted ||
      state == WalSyncDisplayState.outsideRecoveryWindow ||
      state == WalSyncDisplayState.unsupportedAudio ||
      state == WalSyncDisplayState.uploadRejected;

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

  /// Row subtitle colour and label. Black and white like the rest of Settings:
  /// the default tertiary line for neutral and active states, amber for an
  /// automatic retry, red for failed and unrecoverable recordings.
  (Color?, String) _rowVisual(WalSyncDisplayState state) {
    final l = context.l10n;
    return switch (state) {
      WalSyncDisplayState.synced => (null, l.syncStatusConversationCreated),
      WalSyncDisplayState.syncing => (null, l.syncStatusBackingUp),
      WalSyncDisplayState.uploaded => (null, l.syncStatusUploaded),
      WalSyncDisplayState.waiting => (null, l.syncStatusWaiting),
      WalSyncDisplayState.retrying => (OmiColors.warning, l.syncStatusRetrying),
      WalSyncDisplayState.failed => (OmiColors.danger, l.syncStatusFailed),
      WalSyncDisplayState.corrupted => (OmiColors.danger, l.syncStatusFileUnavailable),
      WalSyncDisplayState.outsideRecoveryWindow => (OmiColors.danger, l.syncStatusTooOld),
      WalSyncDisplayState.unsupportedAudio => (OmiColors.danger, l.syncStatusUnsupportedAudio),
      WalSyncDisplayState.uploadRejected => (OmiColors.danger, l.failedStatus),
    };
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
              Text(l.syncFlowIntro, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.45)),
              const SizedBox(height: OmiSpacing.lg),
              _syncFlowStep(1, l.syncStepUpload, l.syncStepUploadDesc),
              const SizedBox(height: OmiSpacing.md),
              _syncFlowStep(2, l.syncStepProcess, l.syncStepProcessDesc),
              const SizedBox(height: OmiSpacing.md),
              _syncFlowStep(3, l.syncStepBackedUp, l.syncStepBackedUpDesc),
              const SizedBox(height: OmiSpacing.lg),
              Text(l.syncFailureFootnote,
                  style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.45)),
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
        const SizedBox(width: OmiSpacing.xs),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.body.copyWith(fontWeight: FontWeight.w500)),
              const SizedBox(height: 2),
              Text(desc, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.45)),
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
        onToggleAutoRemove: (value) async {
          SharedPreferencesUtil().autoRemoveSyncedCopies = value;
          if (value) {
            // Apply immediately: expired copies should not wait for the next
            // sync pass or app restart.
            await context.read<SyncProvider>().applySyncedCopyRetention();
          }
          if (context.mounted) setState(() {});
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
  final ValueChanged<bool> onToggleAutoRemove;

  const _ManageStorageSheet({
    required this.provider,
    required this.onClearSynced,
    required this.onClearPending,
    required this.onClearAll,
    required this.onToggleAutoRemove,
  });

  @override
  Widget build(BuildContext context) {
    final syncedCount = provider.syncedWals.length;
    final pendingCount = provider.pendingDeletableWals.length;
    final totalCount = provider.clearableWalsCount;
    final autoRemoveOn = SharedPreferencesUtil().autoRemoveSyncedCopies;

    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _StorageRow(
            icon: FontAwesomeIcons.circleCheck,
            title: context.l10n.synced,
            subtitle: context.l10n.safelyBackedUp,
            count: syncedCount,
            onClear: syncedCount > 0 ? onClearSynced : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: OmiSpacing.sm),
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            title: context.l10n.pending,
            subtitle: context.l10n.notYetSynced,
            count: pendingCount,
            onClear: pendingCount > 0 ? onClearPending : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: OmiSpacing.sm),
          _AutoRemoveRow(
            initialValue: autoRemoveOn,
            onChanged: onToggleAutoRemove,
          ),
          if (totalCount > 0) ...[
            const SizedBox(height: OmiSpacing.lg),
            OmiButton.destructive(label: context.l10n.clearAll, expand: true, onPressed: onClearAll),
          ],
        ],
      ),
    );
  }
}

/// The auto-remove preference, surfaced beside the clear actions it governs so
/// the two ways of reclaiming synced-copy space read as one set. Persists
/// through [SharedPreferencesUtil.autoRemoveSyncedCopies]; both this sheet and
/// the Offline Sync settings page write the same key, and each rereads it on
/// build so neither can drift from the stored value. The row holds the tapped
/// value itself: the sheet around it is stateless and does not rebuild when
/// only the switch flips, so without local state the knob would snap back
/// while the stored preference had already changed.
class _AutoRemoveRow extends StatefulWidget {
  final bool initialValue;
  final ValueChanged<bool> onChanged;

  const _AutoRemoveRow({required this.initialValue, required this.onChanged});

  @override
  State<_AutoRemoveRow> createState() => _AutoRemoveRowState();
}

class _AutoRemoveRowState extends State<_AutoRemoveRow> {
  late bool _value = widget.initialValue;

  @override
  Widget build(BuildContext context) {
    final days = SharedPreferencesUtil().autoRemoveSyncedCopiesDays;
    return ClipRRect(
      borderRadius: OmiRadius.lgAll,
      child: Material(
        color: OmiColors.surface2,
        child: OmiSettingsRow.toggle(
          leading: const OmiSettingsIconTile(Icon(Icons.auto_delete)),
          title: context.l10n.autoRemoveSyncedCopiesTitle,
          subtitle: context.l10n.autoRemoveSyncedCopiesDays(days),
          value: _value,
          onChanged: (value) {
            setState(() => _value = value);
            widget.onChanged(value);
          },
        ),
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  final FaIconData icon;
  final String title;
  final String subtitle;
  final int count;
  final VoidCallback? onClear;
  final String clearLabel;

  const _StorageRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: Row(
        children: [
          OmiSettingsIconTile(FaIcon(icon)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(child: Text(title, style: OmiType.body.copyWith(fontWeight: FontWeight.w500))),
                    const SizedBox(width: OmiSpacing.xs),
                    Text('$count', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
                const SizedBox(height: 2),
                Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
              ],
            ),
          ),
          if (onClear != null) ...[
            const SizedBox(width: OmiSpacing.sm),
            OmiButton.destructive(label: clearLabel, size: OmiButtonSize.compact, onPressed: onClear),
          ],
        ],
      ),
    );
  }
}
