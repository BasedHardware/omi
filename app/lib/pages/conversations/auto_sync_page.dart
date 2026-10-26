import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/pages/conversations/widgets/device_download_meter.dart';
import 'package:omi/pages/conversations/widgets/device_storage_card.dart';
import 'package:omi/pages/conversations/widgets/sync_details_sheet.dart';
import 'package:omi/pages/conversations/widgets/sync_step_bar.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';
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
  // Two tabs: what still has to sync (including recordings that need the
  // user), and what already has. Landing on To sync shows the small actionable
  // set; the list below is sliver-lazy, so Synced is safe with thousands.
  WalDisplayFilter _filter = WalDisplayFilter.pending;

  final SyncRunTracker _runTracker = SyncRunTracker();

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
        // Compute the lists once per build and pass them down — the
        // SliverList.builder uses them via index, so filtering again inside
        // itemBuilder would re-sort+re-filter on every visible row.
        final toSync = hasAnyRecording
            ? syncProvider.displaySortedWals.where((w) => w.syncDisplayState != WalSyncDisplayState.synced).toList()
            : const <Wal>[];
        final filteredWals = !hasAnyRecording
            ? const <Wal>[]
            : _filter == WalDisplayFilter.synced
                ? syncProvider.walsForDisplayFilter(WalDisplayFilter.synced)
                : toSync;

        return Scaffold(
          // One name for the device-storage sync screen everywhere: "Offline Sync", as Settings calls it.
          // No app bar actions: "How syncing works" lives in Sync details, Manage Storage in the Storage group.
          appBar: AppBar(
            leading: const OmiBackButton(),
            title: Text(context.l10n.offlineSync),
          ),
          body: CustomScrollView(
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverList(
                  delegate: SliverChildListDelegate.fixed([
                    const SizedBox(height: 8),
                    _buildOverallStatusCard(syncProvider, syncState),
                    if (syncState.hasError) ...[const SizedBox(height: 16), _buildErrorCard(syncState, syncProvider)],
                    if (WalSyncs.isRingBufferFirmware(deviceProvider.currentFirmwareVersion) &&
                        deviceProvider.ringStatus != null) ...[
                      const SizedBox(height: 16),
                      DeviceStorageCard(status: deviceProvider.ringStatus!),
                    ],
                    const SizedBox(height: 32),
                    _buildStorageSettings(userProvider, syncProvider),
                    if (hasAnyRecording) ...[
                      const SizedBox(height: 32),
                      _buildFilterChips(walSeconds(toSync.where(walIsSyncable))),
                      const SizedBox(height: 4),
                    ],
                  ]),
                ),
              ),
              if (hasAnyRecording) _buildWalListSliver(syncProvider, groupRecordingBlocks(filteredWals)),
              const SliverToBoxAdapter(child: SizedBox(height: 48)),
            ],
          ),
        );
      },
    );
  }

  // ─────────────────────────────────────────
  // Overall status card
  // ─────────────────────────────────────────

  /// Every amount on this card is audio length. File, upload-part and server-job
  /// counts used to leak through ("Processing 0/5914"); they are in Sync details now.
  Widget _buildOverallStatusCard(SyncProvider p, SyncState s) {
    final l = context.l10n;
    String dur(int seconds) => OmiDuration.compact(seconds, l);
    final step = _runTracker.update(s, p.allWals);
    final uploaded = p.uploadedWals.length;
    final sorted = p.displaySortedWals;
    final attentionWals = sorted.where((w) => _needsAttention(w.syncDisplayState)).toList();
    final readyWals = sorted
        .where(
          (w) =>
              w.syncDisplayState == WalSyncDisplayState.waiting || w.syncDisplayState == WalSyncDisplayState.retrying,
        )
        .toList();

    final isActive = s.isSyncing || s.isFetchingConversations;
    final bool showSpinner = (isActive || uploaded > 0) && !p.isRateLimited;

    String title;
    String? subtitle;
    Color titleColor = OmiColors.textPrimary;
    Widget? action;
    SyncStep? barStep;
    double? barFraction;

    Future<void> startSync() async {
      if (await confirmSyncForCustomStt(context) && context.mounted) p.syncWals();
    }

    if (isActive && step != null && step.step != SyncStep.transcribe) {
      final run = _runTracker.runSeconds ?? 0;
      title = run > 0 ? l.syncCardSyncingAmount(dur(run)) : l.syncCardSyncingTitle;
      barStep = step.barStep;
      final known = step.totalSeconds > 0;
      if (step.step == SyncStep.download) {
        subtitle = known ? l.syncStepDownloadingAmount(dur(step.doneSeconds), dur(step.totalSeconds)) : null;
        // The device reports a byte fraction before any audio is countable.
        barFraction = s.progress > 0 ? s.progress : null;
      } else if (s.phase == SyncPhase.waitingForInternet) {
        title = l.syncCardWaitingInternet;
        titleColor = Colors.orangeAccent;
        barFraction = known ? step.fraction : 0;
      } else {
        subtitle = known ? l.syncStepUploadingAmount(dur(step.doneSeconds), dur(step.totalSeconds)) : null;
        barFraction = known && step.doneSeconds > 0 ? step.fraction : null;
      }
      // Live-capture uploads run before the device drain: the bar stays on the device step, unfilled.
      if (barStep != step.step) barFraction = 0;
      action = statusActionPill(l.cancel, Colors.redAccent, () => _confirmCancel(context, p));
    } else if (p.isRateLimited) {
      title = syncCooldownTitle(p.rateLimitReason, l);
      titleColor = Colors.orangeAccent;
    } else if (isActive || uploaded > 0) {
      // Uploads finished; the server is turning them into conversations.
      final job = p.offlineServerProcessingSeconds;
      title = job.totalSeconds > 0 ? l.syncCardTranscribingAmount(dur(job.totalSeconds)) : l.syncCardProcessing;
      subtitle = job.tracked && job.totalSeconds > 0
          ? l.syncCardTranscribedOf(dur(job.doneSeconds), dur(job.totalSeconds))
          : l.syncProcessingBackgroundHint;
      barStep = SyncStep.transcribe;
      barFraction = job.tracked && job.doneSeconds > 0 ? job.doneSeconds / job.totalSeconds : null;
      if (isActive) action = statusActionPill(l.cancel, Colors.redAccent, () => _confirmCancel(context, p));
    } else if (attentionWals.isNotEmpty) {
      title = l.syncCardNeedsAttention(groupRecordingBlocks(attentionWals).length);
      titleColor = Colors.orangeAccent;
      // A deliberate retry re-arms spent budgets and retained request refusals.
      // Missing files and permanent audio/lookback verdicts stay excluded.
      if (p.retryableAttentionWals.isNotEmpty) {
        action = KeyedSubtree(
          key: const Key('offline_sync_card_retry_attention'),
          child: statusActionPill(l.retry, OmiColors.accent, () async {
            if (await confirmSyncForCustomStt(context) && context.mounted) p.retryNeedsAttentionWals();
          }),
        );
      }
    } else if (readyWals.isNotEmpty) {
      final seconds = walSeconds(readyWals);
      title = seconds > 0
          ? l.syncCardReadyAmount(dur(seconds))
          : l.syncCardReadyCount(groupRecordingBlocks(readyWals).length);
      action = statusActionPill(l.sync, OmiColors.accent, startSync);
    } else {
      // All synced, or nothing recorded yet: the same calm baseline, so the card never pops in/out.
      title = l.syncCardAllBackedUp;
      titleColor = OmiColors.active == OmiPalette.light ? OmiColors.textPrimary : Colors.grey.shade400;
    }
    // Independent of the branch above: a sync that created conversations can
    // still leave jobs processing or a recording that needs the user.
    final created = p.syncCompleted ? p.syncedConversationsPointers.length : 0;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 4),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              if (showSpinner) ...[const OmiSpinner(size: OmiSpinnerSize.small), const SizedBox(width: 12)],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: TextStyle(color: titleColor, fontSize: 16, fontWeight: FontWeight.w600, height: 1.25),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w400),
                      ),
                    ],
                  ],
                ),
              ),
              if (action != null) ...[const SizedBox(width: 10), action],
            ],
          ),
          if (barStep != null) ...[
            const SizedBox(height: 14),
            SyncStepBar(step: barStep, fraction: barFraction),
          ],
          const SizedBox(height: 6),
          if (created > 0) ...[
            Divider(height: 1, color: OmiColors.border),
            _cardLink(l.nConversationsCreated(created), () => routeToPage(context, const SyncedConversationsPage())),
          ],
          Divider(height: 1, color: OmiColors.border),
          _cardLink(
            l.syncDetailsTitle,
            () => showSyncDetailsSheet(context, onHowSyncingWorks: () => _showInfoSheet(context)),
          ),
        ],
      ),
    );
  }

  Widget _cardLink(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            Expanded(child: Text(label, style: TextStyle(color: Colors.grey.shade400, fontSize: 14))),
            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12),
          ],
        ),
      ),
    );
  }

  static bool _needsAttention(WalSyncDisplayState s) =>
      s == WalSyncDisplayState.failed ||
      s == WalSyncDisplayState.corrupted ||
      s == WalSyncDisplayState.outsideRecoveryWindow ||
      s == WalSyncDisplayState.unsupportedAudio ||
      s == WalSyncDisplayState.uploadRejected;

  // ─────────────────────────────────────────
  //  Error card
  // ─────────────────────────────────────────

  Widget _buildErrorCard(SyncState syncState, SyncProvider syncProvider) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.redAccent, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              SyncProvider.isPendingUploadError(syncState.errorMessage)
                  ? context.l10n.syncStatusFailed
                  : syncState.errorMessage ?? context.l10n.syncFailed,
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () => syncProvider.retrySync(),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.red.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                context.l10n.retry,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontWeight: FontWeight.w500),
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

  Widget _buildStorageSettings(UserProvider userProvider, SyncProvider syncProvider) {
    final isPhoneOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final isCloudOn = userProvider.privateCloudSyncEnabled;
    final autoRemoveOn = SharedPreferencesUtil().autoRemoveSyncedCopies;
    final autoRemoveDays = SharedPreferencesUtil().autoRemoveSyncedCopiesDays;

    // One group for every storage choice. Auto-remove used to be its own
    // "Local Copies" section, and Manage Storage hid behind an app bar menu
    // that only appeared when something could be cleared.
    return OmiSettingsGroup(
      header: context.l10n.storageSection,
      children: [
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.mobile),
          title: context.l10n.storeAudioOnPhone,
          value: isPhoneOn ? context.l10n.on : context.l10n.off,
          onTap: () => routeToPage(context, const LocalStoragePage()).then((_) => setState(() {})),
        ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.cloud),
          title: context.l10n.storeAudioOnCloud,
          value: isCloudOn ? context.l10n.on : context.l10n.off,
          onTap: () => routeToPage(context, const PrivateCloudSyncPage()),
        ),
        OmiSettingsRow.toggle(
          leading: const Icon(Icons.auto_delete),
          title: context.l10n.autoRemoveSyncedCopiesTitle,
          subtitle: context.l10n.autoRemoveSyncedCopiesDays(autoRemoveDays),
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
        if (syncProvider.clearableWalsCount > 0)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.trashCan),
            title: context.l10n.manageStorage,
            onTap: () => _showManageStorageSheet(context, syncProvider),
          ),
      ],
    );
  }

  // ─────────────────────────────────────────
  // Filter chips + WAL list
  // ─────────────────────────────────────────

  Widget _buildFilterChips(int toSyncSeconds) {
    Widget chip(WalDisplayFilter f, String label) {
      final selected = _filter == f;
      return Expanded(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => setState(() => _filter = f),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 2),
            padding: const EdgeInsets.symmetric(vertical: 8),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: selected ? OmiColors.textPrimary.withValues(alpha: 0.08) : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: selected ? OmiColors.textPrimary : Colors.grey.shade500,
                fontSize: 13,
                fontWeight: selected ? FontWeight.w500 : FontWeight.w400,
              ),
            ),
          ),
        ),
      );
    }

    final pendingLabel = toSyncSeconds > 0
        ? '${context.l10n.pending} · ${OmiDuration.compact(toSyncSeconds, context.l10n)}'
        : context.l10n.pending;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(10)),
      child: Row(
        children: [
          chip(WalDisplayFilter.pending, pendingLabel),
          chip(WalDisplayFilter.synced, context.l10n.synced),
        ],
      ),
    );
  }

  /// Sliver-based list, one card per day under a day label. SliverList.builder
  /// mounts only the rows near the viewport, so a filter with thousands of
  /// items never instantiates thousands of Dismissibles in one frame.
  ///
  /// The card look is drawn per row: a day's first row gets rounded top
  /// corners, its last rounded bottom corners, with dividers between.
  Widget _buildWalListSliver(SyncProvider syncProvider, List<RecordingBlock> blocks) {
    if (blocks.isEmpty) {
      final emptyMsg =
          _filter == WalDisplayFilter.synced ? context.l10n.noSyncedRecordingsYet : context.l10n.noPendingRecordings;
      return SliverPadding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
        sliver: SliverToBoxAdapter(
          child: Container(
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(20)),
            child: Center(
              child: Text(emptyMsg, style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
            ),
          ),
        ),
      );
    }

    final items = _dayItems(blocks);
    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      sliver: SliverList.builder(
        itemCount: items.length,
        itemBuilder: (context, i) => switch (items[i]) {
          _DayLabel(:final label) => Padding(
              padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
              child: Text(
                label,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
              ),
            ),
          _DayRow(:final block, :final isFirst, :final isLast) =>
            _buildBlockListItem(syncProvider, block, i, isFirst: isFirst, isLast: isLast),
        },
      ),
    );
  }

  /// Flattens newest-first recordings into day labels and rows.
  List<_DayItem> _dayItems(List<RecordingBlock> blocks) {
    final dates = OmiDateFormat.of(context);
    final items = <_DayItem>[];
    DateTime? currentDay;
    for (var i = 0; i < blocks.length; i++) {
      final start = DateTime.fromMillisecondsSinceEpoch(blocks[i].startSeconds * 1000).toLocal();
      final day = DateTime(start.year, start.month, start.day);
      final isFirst = day != currentDay;
      if (isFirst) {
        currentDay = day;
        items.add(_DayLabel(dates.dayHeader(start)));
      }
      final next = i + 1 < blocks.length
          ? DateTime.fromMillisecondsSinceEpoch(blocks[i + 1].startSeconds * 1000).toLocal()
          : null;
      final isLast = next == null || DateTime(next.year, next.month, next.day) != day;
      items.add(_DayRow(blocks[i], isFirst: isFirst, isLast: isLast));
    }
    return items;
  }

  /// A one-file recording keeps the swipe-to-delete row; a longer one is a single row that opens
  /// its files, so a continuous recording no longer reads as a column of 75 s and 3 min rows.
  Widget _buildBlockListItem(
    SyncProvider syncProvider,
    RecordingBlock block,
    int i, {
    required bool isFirst,
    required bool isLast,
  }) {
    final wal = block.wals.first;
    final state = wal.syncDisplayState;
    return Container(
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: BorderRadius.vertical(
          top: isFirst ? const Radius.circular(20) : Radius.zero,
          bottom: isLast ? const Radius.circular(20) : Radius.zero,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (block.wals.length > 1)
            _blockRow(block)
          else
            Dismissible(
              // Storage suffix because `wal.id` (device_timerStart) is shared by the
              // SD-card and on-phone copies of one recording. Not the row index: rows
              // shift after a dismiss, and a reused key asserts.
              key: ValueKey('${wal.id}#${wal.storage.name}'),
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
                color: Colors.red,
                child: const Icon(Icons.delete, color: Colors.white),
              ),
              onDismissed: (direction) {
                syncProvider.deleteWal(wal);
              },
              child: _walRow(wal, showDay: false),
            ),
          if (!isLast) _rowDivider,
        ],
      ),
    );
  }

  Widget _blockRow(RecordingBlock block) {
    final state = block.state;
    final (color, label) = _rowLabel(block.representative);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _showBlockFiles(block),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _blockTitle(block, showDay: false),
                    style: _rowTitleStyle(synced: state == WalSyncDisplayState.synced),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _rowSubtitleStyle(color),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            _blockTrailing(block, state),
          ],
        ),
      ),
    );
  }

  /// The row's one action, for the whole recording: Try again re-sends the files that can still
  /// go, Delete removes a recording nothing can move forward. Mixed or healthy blocks open.
  Widget _blockTrailing(RecordingBlock block, WalSyncDisplayState state) {
    if (state == WalSyncDisplayState.syncing) return const OmiSpinner(size: OmiSpinnerSize.small);
    if (block.wals.any((w) =>
        !w.onDeviceOnly &&
        (isRetryableSyncState(w.syncDisplayState) || w.syncDisplayState == WalSyncDisplayState.retrying))) {
      return OmiButton.secondary(
        label: context.l10n.tryAgain,
        size: OmiButtonSize.compact,
        onPressed: () async {
          final sync = context.read<SyncProvider>();
          for (final wal in block.wals) {
            final s = wal.syncDisplayState;
            if (!wal.onDeviceOnly && (isRetryableSyncState(s) || s == WalSyncDisplayState.retrying)) {
              await sync.syncWal(wal);
            }
          }
        },
      );
    }
    if (block.wals.every((w) => _isUnsyncableState(w.syncDisplayState))) {
      return OmiButton.destructive(
        label: context.l10n.delete,
        size: OmiButtonSize.compact,
        onPressed: () => _confirmDeleteWals(block.wals),
      );
    }
    return FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12);
  }

  // One title, subtitle and divider for file rows and recording rows, so the two never drift.
  static const _rowDivider = Divider(height: 1, color: Color(0xFF2C2C2E), indent: 16, endIndent: 16);

  static TextStyle _rowTitleStyle({required bool synced}) => TextStyle(
        color: synced ? Colors.grey.shade500 : OmiColors.textPrimary,
        fontSize: 15,
        fontWeight: FontWeight.w500,
      );

  static TextStyle _rowSubtitleStyle(Color color) => TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w400);

  /// The list sits under day labels, so its rows drop the day; the files sheet keeps it.
  String _blockTitle(RecordingBlock block, {bool showDay = true}) {
    final date = DateTime.fromMillisecondsSinceEpoch(block.startSeconds * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final duration = OmiDuration.compact(block.seconds, context.l10n);
    return showDay
        ? '${dates.dayHeader(date)} \u00b7 ${dates.time(date)} \u00b7 $duration'
        : '${dates.time(date)} \u00b7 $duration';
  }

  /// The files behind one recording, each with its own row, detail page and actions.
  void _showBlockFiles(RecordingBlock block) {
    final ids = block.wals.map((w) => '${w.id}#${w.storage.name}').toSet();
    final sync = context.read<SyncProvider>();
    showOmiSheet<void>(
      context: context,
      title: _blockTitle(block),
      // The page's provider, not a lookup from the sheet's own route.
      builder: (sheetContext) => ListenableBuilder(
        listenable: sync,
        builder: (_, __) {
          final wals = sync.displaySortedWals.where((w) => ids.contains('${w.id}#${w.storage.name}')).toList();
          if (wals.isEmpty) return const SizedBox.shrink();
          // Audio still on the device has nothing on the phone to share yet.
          final onPhone = wals.where((w) => w.storage != WalStorage.sdcard && sync.canPlayOrShareWal(w)).toList();
          return ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.of(sheetContext).size.height * 0.7),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (onPhone.isNotEmpty)
                  OmiSettingsRow(
                    leading: const Icon(Icons.ios_share_rounded),
                    title: context.l10n.shareRecording,
                    showChevron: false,
                    onTap: () => _shareRecording(sync, onPhone),
                  ),
                Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: wals.length,
                    separatorBuilder: (_, __) => _rowDivider,
                    itemBuilder: (_, i) => _walRow(wals[i]),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  /// The whole recording as one audio file, instead of one share per short file.
  Future<void> _shareRecording(SyncProvider sync, List<Wal> wals) async {
    try {
      await sync.shareRecordingAsWav(wals);
    } catch (e) {
      Logger.error('Offline Sync: failed to share recording audio: $e');
      if (mounted) OmiFeedback.error(context, context.l10n.audioPlaybackFailed);
    }
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

  Widget _walRow(Wal wal, {bool showDay = true}) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final dates = OmiDateFormat.of(context);
    final timeStr = dates.time(date);
    final dateStr = dates.dayHeader(date);
    final duration = wal.seconds > 0 ? OmiDuration.compact(wal.seconds, context.l10n) : null;

    final state = wal.syncDisplayState;
    final (color, label) = _rowLabel(wal);
    final isSynced = state == WalSyncDisplayState.synced;

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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${showDay ? '$dateStr \u00b7 ' : ''}$timeStr${duration != null ? ' \u00b7 $duration' : ''}',
                    style: _rowTitleStyle(synced: isSynced),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _rowSubtitleStyle(color),
                  ),
                  if (_rowDownloadFraction(wal) != null) ...[
                    const SizedBox(height: 8),
                    DeviceDownloadMeter(
                      fraction: _rowDownloadFraction(wal)!,
                      showReadout: false,
                      barHeight: 4,
                    ),
                  ],
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

  (Color, String) _rowLabel(Wal wal) {
    final state = wal.syncDisplayState;
    var (color, _, label) = _rowVisual(state);
    // On-device WALs surface their transfer state instead of "Waiting to sync".
    final onDevice = wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;
    if (state == WalSyncDisplayState.waiting && onDevice) {
      final phase = context.read<SyncProvider>().syncState.phase;
      label = phase == SyncPhase.downloadingFromDevice
          ? context.l10n.syncStatusDownloadingFromDevice
          : context.l10n.syncStatusOnDevice;
    }
    return (color, label);
  }

  Widget _rowTrailing(Wal wal, WalSyncDisplayState state) {
    if (state == WalSyncDisplayState.syncing) {
      return const OmiSpinner(size: OmiSpinnerSize.small);
    }
    if (!wal.onDeviceOnly && (isRetryableSyncState(state) || state == WalSyncDisplayState.retrying)) {
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
    return FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12);
  }

  /// Confirmed audio/window verdicts no upload can resolve. Spent budgets and
  /// request refusals deliberately remain outside this set: they keep Retry.
  static bool _isUnsyncableState(WalSyncDisplayState state) =>
      state == WalSyncDisplayState.corrupted ||
      state == WalSyncDisplayState.outsideRecoveryWindow ||
      state == WalSyncDisplayState.unsupportedAudio;

  Future<void> _confirmDeleteWals(List<Wal> wals) async {
    final syncProvider = context.read<SyncProvider>();
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteRecording,
      message: context.l10n.thisCannotBeUndone,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (!confirmed) return;
    for (final wal in wals) {
      await syncProvider.deleteWal(wal);
    }
  }

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
        return (Colors.grey.shade500, FontAwesomeIcons.cloudArrowUp, context.l10n.statusProcessed);
      case WalSyncDisplayState.syncing:
        return (Colors.grey.shade300, FontAwesomeIcons.arrowsRotate, context.l10n.syncStatusBackingUp);
      case WalSyncDisplayState.uploaded:
        return (Colors.grey.shade400, FontAwesomeIcons.cloud, context.l10n.syncStatusUploaded);
      case WalSyncDisplayState.waiting:
        return (Colors.grey.shade500, FontAwesomeIcons.cloudArrowUp, context.l10n.syncStatusWaiting);
      case WalSyncDisplayState.retrying:
        return (Colors.orangeAccent, FontAwesomeIcons.arrowsRotate, context.l10n.syncStatusRetrying);
      case WalSyncDisplayState.failed:
        return (Colors.redAccent, FontAwesomeIcons.circleExclamation, context.l10n.syncStatusFailed);
      case WalSyncDisplayState.corrupted:
        return (Colors.redAccent, FontAwesomeIcons.triangleExclamation, context.l10n.syncStatusFileUnavailable);
      case WalSyncDisplayState.outsideRecoveryWindow:
        return (Colors.redAccent, FontAwesomeIcons.clockRotateLeft, context.l10n.syncStatusTooOld);
      case WalSyncDisplayState.unsupportedAudio:
        return (Colors.redAccent, FontAwesomeIcons.fileCircleExclamation, context.l10n.syncStatusUnsupportedAudio);
      case WalSyncDisplayState.uploadRejected:
        return (Colors.redAccent, FontAwesomeIcons.circleExclamation, context.l10n.failedStatus);
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
              Text(l.syncFlowIntro, style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.45)),
              const SizedBox(height: 22),
              _syncFlowStep(1, l.syncStepUpload, l.syncStepUploadDesc),
              const SizedBox(height: 16),
              _syncFlowStep(2, l.syncStepProcess, l.syncStepProcessDesc),
              const SizedBox(height: 16),
              _syncFlowStep(3, l.syncStepBackedUp, l.syncStepBackedUpDesc),
              const SizedBox(height: 22),
              Text(l.syncFailureFootnote, style: TextStyle(color: Colors.grey.shade500, fontSize: 13, height: 1.45)),
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
              Text(desc, style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.45)),
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
            iconColor: Colors.green,
            title: context.l10n.synced,
            subtitle: context.l10n.safelyBackedUp,
            count: syncedCount,
            onClear: syncedCount > 0 ? onClearSynced : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: 12),
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            iconColor: Colors.orange,
            title: context.l10n.pending,
            subtitle: context.l10n.notYetSynced,
            count: pendingCount,
            onClear: pendingCount > 0 ? onClearPending : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: 12),
          _AutoRemoveRow(initialValue: autoRemoveOn, onChanged: onToggleAutoRemove),
          if (totalCount > 0) ...[
            const SizedBox(height: 20),
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
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: OmiSettingsRow.toggle(
        leading: const Icon(Icons.auto_delete),
        title: context.l10n.autoRemoveSyncedCopiesTitle,
        subtitle: context.l10n.autoRemoveSyncedCopiesDays(days),
        value: _value,
        onChanged: (value) {
          setState(() => _value = value);
          widget.onChanged(value);
        },
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

  const _StorageRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(color: iconColor.withValues(alpha: 0.15), borderRadius: OmiRadius.mdAll),
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
                      style: OmiType.subhead.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                      child: Text('$count', style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(subtitle, style: OmiType.caption.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
          if (onClear != null)
            GestureDetector(
              onTap: onClear,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.pillAll),
                child: Text(
                  clearLabel,
                  style: OmiType.footnote.copyWith(color: OmiColors.danger, fontWeight: FontWeight.w500),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

sealed class _DayItem {}

class _DayLabel extends _DayItem {
  _DayLabel(this.label);
  final String label;
}

class _DayRow extends _DayItem {
  _DayRow(this.block, {required this.isFirst, required this.isLast});
  final RecordingBlock block;
  final bool isFirst;
  final bool isLast;
}
