import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/sync_confirmation.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SyncProvider>().refreshWals();
      SyncReconciler.instance.poke();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<SyncProvider, UserProvider>(
      builder: (context, syncProvider, userProvider, _) {
        final syncState = syncProvider.syncState;
        final pendingWals = syncProvider.pendingWals;
        final syncedWals = syncProvider.syncedWals;
        final hasAnyRecording = syncProvider.allWals.isNotEmpty;
        // Compute the filtered list once per build and pass it down — the
        // SliverList.builder uses it via index, so calling it again inside
        // itemBuilder would re-sort+re-filter on every visible row.
        final filteredWals = hasAnyRecording ? syncProvider.walsForDisplayFilter(_filter) : const <Wal>[];

        return Scaffold(
          backgroundColor: const Color(0xFF0D0D0D),
          appBar: AppBar(
            backgroundColor: const Color(0xFF0D0D0D),
            elevation: 0,
            centerTitle: true,
            title: Text(context.l10n.sync,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
            leading: IconButton(
              icon: const FaIcon(FontAwesomeIcons.chevronLeft, color: Colors.white, size: 18),
              onPressed: () => Navigator.of(context).pop(),
            ),
            actions: [
              IconButton(
                icon: const FaIcon(FontAwesomeIcons.circleInfo, color: Color(0xFF8E8E93), size: 18),
                onPressed: () => _showInfoSheet(context),
              ),
              if (pendingWals.isNotEmpty || syncedWals.isNotEmpty)
                IconButton(
                  icon: const FaIcon(FontAwesomeIcons.ellipsis, color: Color(0xFF8E8E93), size: 18),
                  onPressed: () => _showManageStorageSheet(context, syncProvider),
                ),
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
                    if (syncState.hasError) ...[
                      const SizedBox(height: 16),
                      _buildErrorCard(syncState, syncProvider),
                    ],
                    const SizedBox(height: 32),
                    _buildStorageSettings(userProvider),
                    if (hasAnyRecording) ...[
                      const SizedBox(height: 32),
                      _buildRecordingsHeader(filteredWals.length),
                      const SizedBox(height: 10),
                      _buildFilterChips(),
                      const SizedBox(height: 12),
                    ],
                  ]),
                ),
              ),
              if (hasAnyRecording) _buildWalListSliver(syncProvider, filteredWals),
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

  Widget _buildOverallStatusCard(SyncProvider p, SyncState s) {
    final l = context.l10n;
    final attention = p.needsAttentionWalsCount;
    final uploaded = p.uploadedWals.length;
    final readyToBackUp = p.displaySortedWals
        .where((w) =>
            w.syncDisplayState == WalSyncDisplayState.waiting || w.syncDisplayState == WalSyncDisplayState.retrying)
        .length;
    final hasAnyRecording = p.allWals.isNotEmpty;

    final isActive = s.isSyncing || s.isFetchingConversations;
    final bool showSpinner = (isActive || uploaded > 0) && !p.isRateLimited;

    String title;
    String? progressText;
    Color titleColor = Colors.white;
    Widget? action;

    if (isActive) {
      switch (s.phase) {
        case SyncPhase.downloadingFromDevice:
          title = l.syncCardDownloadingTitle;
          final cur = s.currentFile ?? 0;
          final tot = s.totalFiles ?? 0;
          if (tot > 0) progressText = l.syncCardProgressOf(cur, tot);
          break;
        case SyncPhase.waitingForInternet:
          title = l.syncCardWaitingInternet;
          titleColor = Colors.orangeAccent;
          break;
        case SyncPhase.uploadingToCloud:
          title = l.syncCardUploadingTitle;
          final cur = s.currentFile ?? 0;
          final tot = s.totalFiles ?? 0;
          if (tot > 0) progressText = l.syncCardProgressOf(cur, tot);
          break;
        case SyncPhase.processingOnServer:
          title = l.syncCardProcessing;
          break;
        default:
          title = s.isFetchingConversations ? l.syncCardProcessing : l.syncCardUploadingTitle;
      }
      action = _statusActionPill(l.cancel, Colors.redAccent, () => _confirmCancel(context, p));
    } else if (p.isRateLimited) {
      title = p.rateLimitReason == RateLimitReason.backendBusy ? l.syncCardBackendBusy : l.syncCardRateLimited;
      titleColor = Colors.orangeAccent;
    } else if (uploaded > 0) {
      // Uploads finished, reconciler is resolving jobs in the background.
      title = l.syncCardProcessing;
    } else if (attention > 0) {
      title = l.syncCardNeedsAttention(attention);
      titleColor = Colors.orangeAccent;
      action = _statusActionPill(l.sync, Colors.deepPurpleAccent, () async {
        if (await confirmSyncForCustomStt(context)) p.syncWals();
      });
    } else if (readyToBackUp > 0) {
      title = l.syncCardReadyCount(readyToBackUp);
      action = _statusActionPill(l.sync, Colors.deepPurpleAccent, () async {
        if (await confirmSyncForCustomStt(context)) p.syncWals();
      });
    } else if (hasAnyRecording) {
      title = l.syncCardAllBackedUp;
      titleColor = Colors.grey.shade400;
    } else {
      // No recordings — same calm baseline; the card never pops in/out.
      title = l.syncCardAllBackedUp;
      titleColor = Colors.grey.shade400;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          if (showSpinner) ...[
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: TextStyle(color: titleColor, fontSize: 15, fontWeight: FontWeight.w500, height: 1.25),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (progressText != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    progressText,
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w400),
                  ),
                ],
              ],
            ),
          ),
          if (action != null) ...[const SizedBox(width: 10), action],
        ],
      ),
    );
  }

  Widget _statusActionPill(String label, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(100),
        ),
        child: Text(label, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500)),
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
        decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: Colors.green.withValues(alpha: 0.15), shape: BoxShape.circle),
              child: const Center(child: FaIcon(FontAwesomeIcons.check, color: Colors.green, size: 14)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                context.l10n.nConversationsCreated(count),
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
              ),
            ),
            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12),
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
        color: Colors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.redAccent, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(syncState.errorMessage ?? context.l10n.syncFailed,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13)),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () => syncProvider.retrySync(),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration:
                  BoxDecoration(color: Colors.red.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(100)),
              child: Text(context.l10n.retry,
                  style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontWeight: FontWeight.w500)),
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────
  // Storage settings
  // ─────────────────────────────────────────

  Widget _buildStorageSettings(UserProvider userProvider) {
    final isPhoneOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final isCloudOn = userProvider.privateCloudSyncEnabled;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Text(context.l10n.storageSection,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w500)),
        ),
        Container(
          decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
          child: Column(
            children: [
              _settingRow(
                icon: FontAwesomeIcons.mobile,
                label: context.l10n.storeAudioOnPhone,
                isOn: isPhoneOn,
                onTap: () {
                  Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => const LocalStoragePage()))
                      .then((_) => setState(() {}));
                },
              ),
              const Divider(height: 1, color: Color(0xFF3C3C43), indent: 52),
              _settingRow(
                icon: FontAwesomeIcons.cloud,
                label: context.l10n.storeAudioOnCloud,
                isOn: isCloudOn,
                onTap: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PrivateCloudSyncPage())),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _settingRow({
    required IconData icon,
    required String label,
    required bool isOn,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        child: Row(
          children: [
            FaIcon(icon, color: const Color(0xFF8E8E93), size: 18),
            const SizedBox(width: 14),
            Expanded(
              child:
                  Text(label, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w400)),
            ),
            Text(
              isOn ? context.l10n.on : context.l10n.off,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 14, fontWeight: FontWeight.w400),
            ),
            const SizedBox(width: 10),
            FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────
  // Filter chips + WAL list
  // ─────────────────────────────────────────

  Widget _buildRecordingsHeader(int total) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 2),
      child: Row(
        children: [
          Text(
            context.l10n.recordings,
            style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w500),
          ),
          const SizedBox(width: 8),
          Text('$total', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
          const Spacer(),
          Text(
            context.l10n.newestFirst,
            style: TextStyle(color: Colors.grey.shade600, fontSize: 11, fontWeight: FontWeight.w400),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChips() {
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
              color: selected ? Colors.white.withValues(alpha: 0.08) : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              label,
              style: TextStyle(
                color: selected ? Colors.white : Colors.grey.shade500,
                fontSize: 13,
                fontWeight: selected ? FontWeight.w500 : FontWeight.w400,
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          chip(WalDisplayFilter.all, context.l10n.all),
          chip(WalDisplayFilter.pending, context.l10n.pending),
          chip(WalDisplayFilter.synced, context.l10n.synced),
        ],
      ),
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
          child: Container(
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
            child: Center(
              child: Text(emptyMsg, style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
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
    final isFirst = i == 0;
    final isLast = i == wals.length - 1;
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(
          top: isFirst ? const Radius.circular(20) : Radius.zero,
          bottom: isLast ? const Radius.circular(20) : Radius.zero,
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
            direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
            confirmDismiss: (direction) {
              final uploading = wal.syncDisplayState == WalSyncDisplayState.uploaded;
              return OmiConfirmDialog.show(
                context,
                title: uploading ? context.l10n.deleteWhileProcessingTitle : context.l10n.deleteRecording,
                message: uploading ? context.l10n.deleteWhileProcessingMessage : context.l10n.thisCannotBeUndone,
                confirmLabel: context.l10n.delete,
                confirmColor: Colors.red,
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
            child: _walRow(wal),
          ),
          if (!isLast) const Divider(height: 1, color: Color(0xFF2C2C2E), indent: 16, endIndent: 16),
        ],
      ),
    );
  }

  Widget _walRow(Wal wal) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final timeStr = dateTimeFormat('h:mm a', date);
    final dateStr = '${_monthName(date.month)} ${date.day}';
    final duration = wal.seconds > 0 ? _fmtDuration(wal.seconds) : null;

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
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(context.l10n.syncInProgress), duration: const Duration(seconds: 2)),
          );
          return;
        }
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => WalItemDetailPage(wal: wal)));
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
                    '$dateStr \u00b7 $timeStr${duration != null ? ' \u00b7 $duration' : ''}',
                    style: TextStyle(
                      color: isSynced ? Colors.grey.shade500 : Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w400),
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
      return const SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent)),
      );
    }
    if (state == WalSyncDisplayState.failed || state == WalSyncDisplayState.retrying) {
      return GestureDetector(
        onTap: () => context.read<SyncProvider>().syncWal(wal),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(100),
          ),
          child: Text(context.l10n.retry,
              style: const TextStyle(color: Colors.deepPurpleAccent, fontSize: 13, fontWeight: FontWeight.w500)),
        ),
      );
    }
    return FaIcon(FontAwesomeIcons.chevronRight, color: Colors.grey.shade600, size: 12);
  }

  /// Row subtitle (color, icon, label). Colors stay restrained: grey for
  /// neutral/active, amber for auto-retry, red for failed/corrupted. Purple
  /// is reserved for actions and the spinner — not body text.
  (Color, IconData, String) _rowVisual(WalSyncDisplayState state) {
    switch (state) {
      case WalSyncDisplayState.synced:
        return (Colors.grey.shade500, Icons.cloud_done_rounded, context.l10n.syncStatusConversationCreated);
      case WalSyncDisplayState.syncing:
        return (Colors.grey.shade300, Icons.sync_rounded, context.l10n.syncStatusBackingUp);
      case WalSyncDisplayState.uploaded:
        return (Colors.grey.shade400, Icons.cloud_sync_rounded, context.l10n.syncStatusUploaded);
      case WalSyncDisplayState.waiting:
        return (Colors.grey.shade500, Icons.cloud_upload_outlined, context.l10n.syncStatusWaiting);
      case WalSyncDisplayState.retrying:
        return (Colors.orangeAccent, Icons.autorenew_rounded, context.l10n.syncStatusRetrying);
      case WalSyncDisplayState.failed:
        return (Colors.redAccent, Icons.error_outline_rounded, context.l10n.syncStatusFailed);
      case WalSyncDisplayState.corrupted:
        return (Colors.redAccent, Icons.warning_amber_rounded, context.l10n.syncStatusFileUnavailable);
    }
  }

  // ─────────────────────────────────────────
  // Info bottom sheet
  // ─────────────────────────────────────────

  void _showInfoSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      isScrollControlled: true,
      builder: (context) {
        final l = context.l10n;
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 36,
                    height: 4,
                    decoration: BoxDecoration(color: const Color(0xFF3C3C43), borderRadius: BorderRadius.circular(2)),
                  ),
                ),
                const SizedBox(height: 22),
                Text(l.howSyncingWorks,
                    style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600)),
                const SizedBox(height: 10),
                Text(
                  l.syncFlowIntro,
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.45),
                ),
                const SizedBox(height: 22),
                _syncFlowStep(1, l.syncStepUpload, l.syncStepUploadDesc),
                const SizedBox(height: 16),
                _syncFlowStep(2, l.syncStepProcess, l.syncStepProcessDesc),
                const SizedBox(height: 16),
                _syncFlowStep(3, l.syncStepBackedUp, l.syncStepBackedUpDesc),
                const SizedBox(height: 22),
                Text(
                  l.syncFailureFootnote,
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13, height: 1.45),
                ),
              ],
            ),
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
            style: const TextStyle(color: Colors.deepPurpleAccent, fontSize: 15, fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
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
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _ManageStorageSheet(
        provider: provider,
        onClearSynced: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deleteSyncedFiles,
            message: context.l10n.deleteSyncedFilesMessage,
            confirmLabel: context.l10n.clear,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllSyncedWals();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(context.l10n.syncedFilesDeleted), backgroundColor: Colors.green));
            }
          }
        },
        onClearPending: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deletePendingFiles,
            message: context.l10n.deletePendingFilesWarning,
            confirmLabel: context.l10n.clear,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllPendingWals();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(context.l10n.pendingFilesDeleted), backgroundColor: Colors.green));
            }
          }
        },
        onClearAll: () async {
          Navigator.of(sheetContext).pop();
          final confirmed = await OmiConfirmDialog.show(
            context,
            title: context.l10n.deleteAllFiles,
            message: context.l10n.deleteAllFilesWarning,
            confirmLabel: context.l10n.clearAll,
            confirmColor: Colors.red,
          );
          if (confirmed == true && context.mounted) {
            await provider.deleteAllSyncedWals();
            await provider.deleteAllPendingWals();
            if (context.mounted) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text(context.l10n.allFilesDeleted), backgroundColor: Colors.green));
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
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.cancelSyncQuestion,
      message: context.l10n.filesDownloadedUploadedNextTime,
      confirmLabel: context.l10n.cancelSync,
      cancelLabel: context.l10n.keepSyncing,
    );
    if (confirmed == true) {
      syncProvider.cancelSync();
    }
  }

  String _fmtDuration(int seconds) {
    if (seconds < 60) return '${seconds}s';
    final m = seconds ~/ 60;
    final s = seconds % 60;
    if (m < 60) return s > 0 ? '${m}m ${s}s' : '${m}m';
    final h = m ~/ 60;
    final rm = m % 60;
    return rm > 0 ? '${h}h ${rm}m' : '${h}h';
  }

  String _monthName(int month) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return months[month - 1];
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
    final totalCount = syncedCount + pendingCount;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(height: 20),
              Text(
                context.l10n.manageStorage,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 24),
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
                isWarning: true,
              ),
              if (totalCount > 0) ...[
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: TextButton(
                    onPressed: onClearAll,
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(color: Colors.red.withValues(alpha: 0.3)),
                      ),
                    ),
                    child: Text(
                      context.l10n.clearAll,
                      style: TextStyle(color: Colors.red.shade300, fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  final IconData icon;
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
      decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(16)),
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
                    Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text('$count', style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(subtitle, style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
              ],
            ),
          ),
          if (onClear != null)
            GestureDetector(
              onTap: onClear,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: (isWarning ? Colors.orange : Colors.red).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(
                  clearLabel,
                  style: TextStyle(
                    color: isWarning ? Colors.orange : Colors.red.shade300,
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
