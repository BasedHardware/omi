import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

class AutoSyncPage extends StatefulWidget {
  const AutoSyncPage({super.key});

  @override
  State<AutoSyncPage> createState() => _AutoSyncPageState();
}

class _AutoSyncPageState extends State<AutoSyncPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SyncProvider>().refreshWals();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<SyncProvider, DeviceProvider, UserProvider>(
      builder: (context, syncProvider, deviceProvider, userProvider, _) {
        final syncState = syncProvider.syncState;
        final pendingWals = syncProvider.pendingWals;
        final syncedWals = syncProvider.syncedWals;
        final isDeviceConnected = deviceProvider.isConnected;

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
                icon: const Icon(Icons.info_outline, color: Color(0xFF8E8E93), size: 22),
                onPressed: () => _showInfoSheet(context),
              ),
              if (pendingWals.isNotEmpty || syncedWals.isNotEmpty)
                IconButton(
                  icon: const Icon(Icons.more_horiz, color: Color(0xFF8E8E93), size: 22),
                  onPressed: () => _showManageStorageSheet(context, syncProvider),
                ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            children: [
              const SizedBox(height: 8),
              _buildPipelineCard(syncState, pendingWals, isDeviceConnected, syncProvider),
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
              if (pendingWals.isNotEmpty || syncedWals.isNotEmpty) ...[
                const SizedBox(height: 32),
                _buildFilterChips(syncProvider),
                const SizedBox(height: 16),
                _buildFilteredWalList(syncProvider),
              ],
              const SizedBox(height: 48),
            ],
          ),
        );
      },
    );
  }

  // ─────────────────────────────────────────
  // Pipeline card
  // ─────────────────────────────────────────

  Widget _buildPipelineCard(
    SyncState syncState,
    List<Wal> pendingWals,
    bool isDeviceConnected,
    SyncProvider syncProvider,
  ) {
    final isSyncing = syncState.isSyncing || syncState.isFetchingConversations;
    final hasPending = pendingWals.isNotEmpty;
    final (deviceTier, phoneTier, cloudTier) = _tierStates(syncState, isSyncing, pendingWals, isDeviceConnected);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          _buildTierRow(context.l10n.omisStorage, deviceTier, _deviceDetail(syncState, isSyncing, pendingWals)),
          _tierLine(deviceTier),
          _buildTierRow(context.l10n.phoneStorage, phoneTier, _phoneDetail(syncState, isSyncing, pendingWals)),
          _tierLine(phoneTier),
          _buildTierRow(context.l10n.cloudStorage, cloudTier, _cloudDetail(syncState, isSyncing)),
          if (isSyncing) ...[
            const SizedBox(height: 18),
            GestureDetector(
              onTap: () => _confirmCancel(context, syncProvider),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 7),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(context.l10n.cancel,
                    style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontWeight: FontWeight.w500)),
              ),
            ),
          ] else if (hasPending && !syncState.isCompleted) ...[
            const SizedBox(height: 18),
            GestureDetector(
              onTap: () => syncProvider.syncWals(),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 7),
                decoration: BoxDecoration(
                  color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(context.l10n.sync,
                    style: const TextStyle(color: Colors.deepPurpleAccent, fontSize: 13, fontWeight: FontWeight.w500)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  (_TierState, _TierState, _TierState) _tierStates(
      SyncState syncState, bool isSyncing, List<Wal> pendingWals, bool isDeviceConnected) {
    // During active sync — show phase-based states
    if (isSyncing) {
      switch (syncState.phase) {
        case SyncPhase.downloadingFromDevice:
          return (_TierState.completed, _TierState.active, _TierState.pending);
        case SyncPhase.waitingForInternet:
          return (_TierState.completed, _TierState.completed, _TierState.waiting);
        case SyncPhase.uploadingToCloud:
          return (_TierState.completed, _TierState.completed, _TierState.active);
        case SyncPhase.processingOnServer:
          return (_TierState.completed, _TierState.completed, _TierState.active);
        default:
          return (_TierState.completed, _TierState.active, _TierState.pending);
      }
    }
    if (syncState.isFetchingConversations) {
      return (_TierState.completed, _TierState.completed, _TierState.active);
    }

    // Sync completed — all green regardless of remaining device files
    if (syncState.isCompleted) {
      return (_TierState.completed, _TierState.completed, _TierState.completed);
    }

    // Idle — show actual data location
    if (pendingWals.isEmpty) {
      return (_TierState.completed, _TierState.completed, _TierState.completed);
    }

    final deviceWals = pendingWals.where((w) => w.storage == WalStorage.sdcard).toList();
    final phoneWals = pendingWals.where((w) => w.storage == WalStorage.disk || w.storage == WalStorage.mem).toList();

    // Files on device waiting to be downloaded
    if (deviceWals.isNotEmpty && phoneWals.isEmpty) {
      return (
        isDeviceConnected ? _TierState.waiting : _TierState.disconnected,
        _TierState.pending,
        _TierState.pending,
      );
    }

    // Files already on phone waiting to upload to cloud
    if (deviceWals.isEmpty && phoneWals.isNotEmpty) {
      return (_TierState.completed, _TierState.waiting, _TierState.pending);
    }

    // Files on both device and phone
    return (
      isDeviceConnected ? _TierState.waiting : _TierState.disconnected,
      _TierState.waiting,
      _TierState.pending,
    );
  }

  Widget _buildTierRow(String label, _TierState state, String? detail) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          _tierIcon(state),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: state == _TierState.pending ? Colors.grey.shade600 : Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (detail != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(detail, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _tierIcon(_TierState state) {
    switch (state) {
      case _TierState.completed:
        return Container(
          width: 30,
          height: 30,
          decoration: const BoxDecoration(color: Colors.green, shape: BoxShape.circle),
          child: const Icon(Icons.check, color: Colors.white, size: 17),
        );
      case _TierState.active:
        return Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(
            color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
            shape: BoxShape.circle,
          ),
          child: const Padding(
            padding: EdgeInsets.all(6),
            child:
                CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent)),
          ),
        );
      case _TierState.waiting:
        return Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(color: Colors.orange.withValues(alpha: 0.15), shape: BoxShape.circle),
          child: const Icon(Icons.schedule, color: Colors.orangeAccent, size: 16),
        );
      case _TierState.disconnected:
        return Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(color: Colors.orange.withValues(alpha: 0.15), shape: BoxShape.circle),
          child: const Icon(Icons.bluetooth_disabled, color: Colors.orangeAccent, size: 15),
        );
      case _TierState.pending:
        return Container(
          width: 30,
          height: 30,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF3C3C43), width: 1.5),
          ),
        );
    }
  }

  Widget _tierLine(_TierState from) {
    final color = switch (from) {
      _TierState.completed => Colors.green,
      _TierState.active => Colors.deepPurpleAccent,
      _ => const Color(0xFF3C3C43),
    };
    return Padding(
      padding: const EdgeInsets.only(left: 14),
      child: Align(alignment: Alignment.centerLeft, child: Container(width: 2, height: 22, color: color)),
    );
  }

  String? _deviceDetail(SyncState syncState, bool isSyncing, List<Wal> pendingWals) {
    // During download from device — show file progress
    if (isSyncing &&
        syncState.phase == SyncPhase.downloadingFromDevice &&
        syncState.currentFile != null &&
        syncState.totalFiles != null) {
      return '${syncState.currentFile} of ${syncState.totalFiles} files';
    }
    // Idle — show remaining device files
    if (!isSyncing && !syncState.isCompleted) {
      final deviceFiles = pendingWals.where((w) => w.storage == WalStorage.sdcard).toList();
      if (deviceFiles.isNotEmpty) {
        final totalBytes = deviceFiles.fold<int>(0, (s, w) => s + w.storageTotalBytes);
        return '${deviceFiles.length} file${deviceFiles.length == 1 ? '' : 's'} \u00b7 ${_fmtBytes(totalBytes)}';
      }
    }
    return null;
  }

  String? _phoneDetail(SyncState syncState, bool isSyncing, List<Wal> pendingWals) {
    // During download from device — show BLE transfer speed
    if (isSyncing && syncState.phase == SyncPhase.downloadingFromDevice) {
      final speed = syncState.speedKBps;
      return speed != null && speed > 0 ? '${speed.toStringAsFixed(1)} KB/s' : context.l10n.transferring;
    }
    // During upload to cloud — phone data is ready
    if (isSyncing && syncState.phase == SyncPhase.uploadingToCloud) {
      return null;
    }
    // Idle — show files on phone waiting to upload
    if (!isSyncing && !syncState.isCompleted) {
      final phoneFiles = pendingWals.where((w) => w.storage == WalStorage.disk || w.storage == WalStorage.mem).toList();
      if (phoneFiles.isNotEmpty) {
        return '${phoneFiles.length} file${phoneFiles.length == 1 ? '' : 's'} waiting to upload';
      }
    }
    return null;
  }

  String? _cloudDetail(SyncState syncState, bool isSyncing) {
    // Server is processing segments
    if (isSyncing && syncState.phase == SyncPhase.processingOnServer) {
      final current = syncState.currentFile;
      final total = syncState.totalFiles;
      if (current != null && total != null && total > 0) {
        return context.l10n.processingOnServerProgress(current, total);
      }
      return context.l10n.processingOnServer;
    }
    // During upload — show file count progress
    if (isSyncing && syncState.phase == SyncPhase.uploadingToCloud) {
      final current = syncState.currentFile;
      final total = syncState.totalFiles;
      if (current != null && total != null && total > 0) {
        return '$current of $total files';
      }
      return context.l10n.transferring;
    }
    // Fetching conversations after upload
    if (syncState.isFetchingConversations) {
      return 'Processing...';
    }
    return null;
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
              child: const Icon(Icons.check, color: Colors.green, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                context.l10n.nConversationsCreated(count),
                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
              ),
            ),
            const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
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
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 20),
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
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: isOn ? Colors.green.withValues(alpha: 0.15) : const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                isOn ? context.l10n.on : context.l10n.off,
                style: TextStyle(
                    color: isOn ? Colors.green : Colors.grey.shade500, fontSize: 12, fontWeight: FontWeight.w500),
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────
  // Filter chips + WAL list
  // ─────────────────────────────────────────

  Widget _buildFilterChips(SyncProvider syncProvider) {
    final pendingCount = syncProvider.pendingWals.length;
    final syncedCount = syncProvider.syncedWals.length;

    return Row(
      children: [
        _chipButton(
          context.l10n.pending,
          syncProvider.statusFilter == WalStatusFilter.pending,
          () => syncProvider.setStatusFilter(WalStatusFilter.pending),
          count: pendingCount,
        ),
        const SizedBox(width: 8),
        _chipButton(
          context.l10n.synced,
          syncProvider.statusFilter == WalStatusFilter.synced,
          () => syncProvider.setStatusFilter(WalStatusFilter.synced),
          count: syncedCount,
        ),
      ],
    );
  }

  Widget _chipButton(String label, bool selected, VoidCallback onTap, {int? count}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? Colors.white.withValues(alpha: 0.12) : const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(100),
          border: selected ? Border.all(color: Colors.white.withValues(alpha: 0.3), width: 1) : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                color: selected ? Colors.white : Colors.grey.shade400,
                fontSize: 14,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
            if (count != null) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: selected ? Colors.white.withValues(alpha: 0.2) : const Color(0xFF2A2A2E),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '$count',
                  style: TextStyle(
                    color: selected ? Colors.white : Colors.grey.shade500,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildFilteredWalList(SyncProvider syncProvider) {
    final wals = syncProvider.filteredByStatusWals;
    final isSyncedFilter = syncProvider.statusFilter == WalStatusFilter.synced;

    if (wals.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
        child: Center(
          child: Text(
            isSyncedFilter ? context.l10n.noSyncedRecordings : context.l10n.noPendingRecordings,
            style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
          ),
        ),
      );
    }

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          for (int i = 0; i < wals.length; i++) ...[
            Dismissible(
              key: Key(wals[i].id),
              direction: wals[i].isSyncing ? DismissDirection.none : DismissDirection.endToStart,
              confirmDismiss: (direction) {
                return OmiConfirmDialog.show(
                  context,
                  title: context.l10n.deleteRecording,
                  message: context.l10n.thisCannotBeUndone,
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
                syncProvider.deleteWal(wals[i]);
              },
              child: _walItem(wals[i], synced: isSyncedFilter),
            ),
            if (i < wals.length - 1) const Divider(height: 1, color: Color(0xFF3C3C43), indent: 52),
          ],
        ],
      ),
    );
  }

  Widget _walItem(Wal wal, {required bool synced}) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final timeStr = dateTimeFormat('h:mm a', date);
    final dateStr = '${_monthName(date.month)} ${date.day}';
    final duration = wal.seconds > 0 ? _fmtDuration(wal.seconds) : null;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        final syncProvider = context.read<SyncProvider>();
        if (syncProvider.isSyncing && wal.storage == WalStorage.sdcard) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Sync in progress'), duration: Duration(seconds: 2)),
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
                    style: TextStyle(color: synced ? Colors.grey.shade400 : Colors.white, fontSize: 14),
                  ),
                  if (wal.isSyncing && wal.syncSpeedKBps != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text('${wal.syncSpeedKBps!.toStringAsFixed(1)} KB/s',
                          style: const TextStyle(color: Colors.deepPurpleAccent, fontSize: 12)),
                    ),
                ],
              ),
            ),
            if (wal.isSyncing)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent)),
              )
            else
              Icon(Icons.chevron_right, color: Colors.grey.shade700, size: 18),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────
  // Info bottom sheet
  // ─────────────────────────────────────────

  void _showInfoSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      isScrollControlled: true,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
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
                const SizedBox(height: 20),
                Text(context.l10n.howSyncingWorks,
                    style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
                const SizedBox(height: 20),
                _infoItem(
                  icon: Icons.memory,
                  color: Colors.deepPurpleAccent,
                  title: context.l10n.omisStorage,
                  desc: context.l10n.omisStorageDesc,
                ),
                const SizedBox(height: 16),
                _infoItem(
                  icon: Icons.phone_iphone,
                  color: Colors.blue,
                  title: context.l10n.phoneStorage,
                  desc: context.l10n.phoneStorageDesc,
                ),
                const SizedBox(height: 16),
                _infoItem(
                  icon: Icons.cloud_done_outlined,
                  color: Colors.green,
                  title: context.l10n.cloudStorage,
                  desc: context.l10n.cloudStorageDesc,
                ),
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.green.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.auto_awesome, color: Colors.green, size: 18),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(context.l10n.recordingsSyncAutomatically,
                            style: const TextStyle(color: Colors.green, fontSize: 13, fontWeight: FontWeight.w500)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _infoItem({required IconData icon, required Color color, required String title, required String desc}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(color: color.withValues(alpha: 0.15), shape: BoxShape.circle),
          child: Icon(icon, color: color, size: 16),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
              const SizedBox(height: 4),
              Text(desc, style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.4)),
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

  String _fmtBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  String _monthName(int month) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return months[month - 1];
  }
}

enum _TierState { completed, active, waiting, disconnected, pending }

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
    final pendingCount = provider.pendingWals.length;
    final totalCount = provider.allWals.length;

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
