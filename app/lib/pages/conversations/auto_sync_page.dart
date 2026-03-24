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
import 'package:omi/utils/other/temp.dart';
import 'synced_conversations_page.dart';

class AutoSyncPage extends StatefulWidget {
  const AutoSyncPage({super.key});

  @override
  State<AutoSyncPage> createState() => _AutoSyncPageState();
}

class _AutoSyncPageState extends State<AutoSyncPage> with SingleTickerProviderStateMixin {
  bool _showHistory = false;

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
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.black,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            title: const Text('Sync', style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
            centerTitle: true,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 18),
              onPressed: () => Navigator.of(context).pop(),
            ),
            actions: [
              IconButton(
                icon: const Icon(Icons.help_outline_rounded, color: Color(0xFF636366), size: 22),
                onPressed: () => _showInfoSheet(context),
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 40),
            children: [
              // -- Status pipeline --
              _buildPipelineCard(syncState, pendingWals, syncedWals, isDeviceConnected, syncProvider),

              // -- Conversations created --
              if (syncProvider.syncCompleted && syncProvider.syncedConversationsPointers.isNotEmpty) ...[
                const SizedBox(height: 12),
                _buildConversationsCard(syncProvider),
              ],

              // -- Error --
              if (syncState.hasError) ...[
                const SizedBox(height: 12),
                _buildErrorCard(syncState, syncProvider),
              ],

              // -- Storage settings --
              const SizedBox(height: 24),
              _buildStorageSettings(userProvider),

              // -- Recordings --
              if (pendingWals.isNotEmpty || syncedWals.isNotEmpty) ...[
                const SizedBox(height: 24),
                _buildRecordingsSection(pendingWals, syncedWals),
              ],
            ],
          ),
        );
      },
    );
  }

  // ═══════════════════════════════════════════════
  //  Pipeline card
  // ═══════════════════════════════════════════════

  Widget _buildPipelineCard(
    SyncState syncState,
    List<Wal> pendingWals,
    List<Wal> syncedWals,
    bool isDeviceConnected,
    SyncProvider syncProvider,
  ) {
    final isSyncing = syncState.isSyncing || syncState.isFetchingConversations;
    final hasPending = pendingWals.isNotEmpty;

    final (deviceTier, phoneTier, cloudTier) = _computeTierStates(syncState, isSyncing, hasPending, isDeviceConnected);

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF141416),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSyncing ? Colors.deepPurpleAccent.withValues(alpha: 0.3) : const Color(0xFF1F1F23),
          width: 1,
        ),
      ),
      child: Column(
        children: [
          // Progress bar
          if (isSyncing)
            ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(15)),
              child: LinearProgressIndicator(
                value: syncState.progress,
                backgroundColor: Colors.transparent,
                valueColor: AlwaysStoppedAnimation<Color>(Colors.deepPurpleAccent.withValues(alpha: 0.8)),
                minHeight: 3,
              ),
            ),

          Padding(
            padding: EdgeInsets.fromLTRB(20, isSyncing ? 20 : 24, 20, 20),
            child: Column(
              children: [
                // Tiers
                _buildTier(Icons.memory_rounded, 'Device', deviceTier, _deviceSubtitle(syncState, isSyncing)),
                _buildConnector(deviceTier),
                _buildTier(
                    Icons.phone_iphone_rounded, 'Phone', phoneTier, _phoneSubtitle(phoneTier, pendingWals, syncState)),
                _buildConnector(phoneTier),
                _buildTier(Icons.cloud_outlined, 'Cloud', cloudTier, _cloudSubtitle(syncState, isSyncing)),

                const SizedBox(height: 20),

                // Status line
                _buildStatusLine(syncState, hasPending, isDeviceConnected, pendingWals.length),

                // Cancel
                if (isSyncing) ...[
                  const SizedBox(height: 14),
                  GestureDetector(
                    onTap: () => _confirmCancel(context, syncProvider),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(100),
                        border: Border.all(color: const Color(0xFF3A3A3E)),
                      ),
                      child: const Text('Stop',
                          style: TextStyle(color: Color(0xFFAEAEB2), fontSize: 13, fontWeight: FontWeight.w500)),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  (_TierState, _TierState, _TierState) _computeTierStates(
      SyncState syncState, bool isSyncing, bool hasPending, bool isDeviceConnected) {
    if (isSyncing) {
      final phase = syncState.phase;
      if (phase == SyncPhase.downloadingFromDevice) {
        return (_TierState.active, _TierState.pending, _TierState.pending);
      } else if (phase == SyncPhase.waitingForInternet) {
        return (_TierState.completed, _TierState.active, _TierState.pending);
      } else if (phase == SyncPhase.uploadingToCloud) {
        return (_TierState.completed, _TierState.completed, _TierState.active);
      }
      return (_TierState.active, _TierState.pending, _TierState.pending);
    }
    if (hasPending) {
      return (isDeviceConnected ? _TierState.waiting : _TierState.disconnected, _TierState.pending, _TierState.pending);
    }
    return (_TierState.completed, _TierState.completed, _TierState.completed);
  }

  Widget _buildTier(IconData icon, String label, _TierState state, String? subtitle) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          _buildTierIcon(state),
          const SizedBox(width: 14),
          Expanded(
            child: Row(
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: state == _TierState.pending ? const Color(0xFF636366) : Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(width: 8),
                  Text(subtitle, style: const TextStyle(color: Color(0xFF636366), fontSize: 12)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTierIcon(_TierState state) {
    const double size = 32;
    switch (state) {
      case _TierState.completed:
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: const Color(0xFF1A3A1A),
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF2D6A2D), width: 1.5),
          ),
          child: const Icon(Icons.check_rounded, color: Color(0xFF4ADE80), size: 18),
        );
      case _TierState.active:
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: Colors.deepPurpleAccent.withValues(alpha: 0.12),
            shape: BoxShape.circle,
            border: Border.all(color: Colors.deepPurpleAccent.withValues(alpha: 0.4), width: 1.5),
          ),
          child: const Padding(
            padding: EdgeInsets.all(7),
            child:
                CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent)),
          ),
        );
      case _TierState.waiting:
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: const Color(0xFF2A2210),
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF6B5A1E), width: 1.5),
          ),
          child: const Icon(Icons.schedule_rounded, color: Color(0xFFFBBF24), size: 16),
        );
      case _TierState.disconnected:
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: const Color(0xFF2A2210),
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF6B5A1E), width: 1.5),
          ),
          child: const Icon(Icons.bluetooth_disabled_rounded, color: Color(0xFFFBBF24), size: 15),
        );
      case _TierState.pending:
        return Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1E),
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF2C2C30), width: 1.5),
          ),
        );
    }
  }

  Widget _buildConnector(_TierState fromState) {
    Color color;
    switch (fromState) {
      case _TierState.completed:
        color = const Color(0xFF2D6A2D);
      case _TierState.active:
        color = Colors.deepPurpleAccent.withValues(alpha: 0.4);
      default:
        color = const Color(0xFF2C2C30);
    }
    return Padding(
      padding: const EdgeInsets.only(left: 15),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
            width: 2, height: 20, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(1))),
      ),
    );
  }

  String? _deviceSubtitle(SyncState syncState, bool isSyncing) {
    if (isSyncing &&
        syncState.phase == SyncPhase.downloadingFromDevice &&
        syncState.speedKBps != null &&
        syncState.speedKBps! > 0) {
      return '${syncState.speedKBps!.toStringAsFixed(1)} KB/s';
    }
    return null;
  }

  String? _phoneSubtitle(_TierState state, List<Wal> pendingWals, SyncState syncState) {
    final phoneFiles = pendingWals.where((w) => w.storage == WalStorage.disk).toList();
    if (phoneFiles.isNotEmpty) {
      final totalBytes = phoneFiles.fold<int>(0, (sum, w) => sum + w.storageTotalBytes);
      return '${phoneFiles.length} file${phoneFiles.length == 1 ? '' : 's'} \u00b7 ${_formatBytes(totalBytes)}';
    }
    return null;
  }

  String? _cloudSubtitle(SyncState syncState, bool isSyncing) {
    if (isSyncing && syncState.phase == SyncPhase.uploadingToCloud) {
      return '${(syncState.progress * 100).toInt()}%';
    }
    return null;
  }

  Widget _buildStatusLine(SyncState syncState, bool hasPending, bool isDeviceConnected, int pendingCount) {
    String text;
    Color color;
    IconData? icon;

    if (syncState.isSyncing) {
      switch (syncState.phase) {
        case SyncPhase.downloadingFromDevice:
          text = 'Downloading from device';
          color = Colors.deepPurpleAccent;
          icon = Icons.arrow_downward_rounded;
        case SyncPhase.waitingForInternet:
          text = 'Waiting for connection';
          color = const Color(0xFFFBBF24);
          icon = Icons.wifi_off_rounded;
        case SyncPhase.uploadingToCloud:
          text = 'Uploading to cloud';
          color = const Color(0xFF60A5FA);
          icon = Icons.cloud_upload_outlined;
        default:
          text = 'Syncing';
          color = Colors.deepPurpleAccent;
          icon = Icons.sync_rounded;
      }
    } else if (syncState.isFetchingConversations) {
      text = 'Creating conversations';
      color = const Color(0xFF60A5FA);
      icon = Icons.auto_awesome_rounded;
    } else if (syncState.hasError) {
      text = 'Sync failed';
      color = const Color(0xFFF87171);
      icon = Icons.error_outline_rounded;
    } else if (hasPending) {
      if (isDeviceConnected) {
        text = '$pendingCount recording${pendingCount == 1 ? '' : 's'} waiting';
        color = const Color(0xFFFBBF24);
        icon = Icons.schedule_rounded;
      } else {
        text = 'Connect device to sync';
        color = const Color(0xFF636366);
        icon = Icons.bluetooth_rounded;
      }
    } else {
      text = 'All recordings synced';
      color = const Color(0xFF4ADE80);
      icon = Icons.check_circle_outline_rounded;
    }

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
        ],
        Text(text, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500)),
      ],
    );
  }

  // ═══════════════════════════════════════════════
  //  Conversations created
  // ═══════════════════════════════════════════════

  Widget _buildConversationsCard(SyncProvider syncProvider) {
    final count = syncProvider.syncedConversationsPointers.length;
    return GestureDetector(
      onTap: () => routeToPage(context, const SyncedConversationsPage()),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF141416),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFF1A3A1A)),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(color: Color(0xFF1A3A1A), shape: BoxShape.circle),
              child: const Icon(Icons.chat_bubble_outline_rounded, color: Color(0xFF4ADE80), size: 17),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$count conversation${count == 1 ? '' : 's'} created',
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                  ),
                  const Text('Tap to view', style: TextStyle(color: Color(0xFF636366), fontSize: 12)),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Color(0xFF3A3A3E), size: 22),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════
  //  Error card
  // ═══════════════════════════════════════════════

  Widget _buildErrorCard(SyncState syncState, SyncProvider syncProvider) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1210),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF5C2020)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: Color(0xFFF87171), size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              syncState.errorMessage ?? 'Sync failed. Tap retry.',
              style: const TextStyle(color: Color(0xFFF87171), fontSize: 13, height: 1.3),
            ),
          ),
          const SizedBox(width: 12),
          GestureDetector(
            onTap: () => syncProvider.retrySync(),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
              decoration: BoxDecoration(
                color: const Color(0xFF5C2020),
                borderRadius: BorderRadius.circular(100),
              ),
              child: const Text('Retry',
                  style: TextStyle(color: Color(0xFFF87171), fontSize: 13, fontWeight: FontWeight.w500)),
            ),
          ),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════════
  //  Storage settings
  // ═══════════════════════════════════════════════

  Widget _buildStorageSettings(UserProvider userProvider) {
    final isPhoneOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final isCloudOn = userProvider.privateCloudSyncEnabled;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(left: 4, bottom: 10),
          child: Text('Storage',
              style:
                  TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
        ),
        Container(
          decoration: BoxDecoration(
            color: const Color(0xFF141416),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF1F1F23)),
          ),
          child: Column(
            children: [
              _buildSettingRow(
                icon: Icons.phone_iphone_rounded,
                iconColor: const Color(0xFF60A5FA),
                label: 'Save audio to phone',
                value: isPhoneOn,
                onTap: () {
                  Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => const LocalStoragePage()))
                      .then((_) => setState(() {}));
                },
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16),
                child: Divider(height: 1, color: Color(0xFF1F1F23)),
              ),
              _buildSettingRow(
                icon: Icons.cloud_outlined,
                iconColor: const Color(0xFF4ADE80),
                label: 'Save audio to cloud',
                value: isCloudOn,
                onTap: () {
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PrivateCloudSyncPage()));
                },
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSettingRow({
    required IconData icon,
    required Color iconColor,
    required String label,
    required bool value,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Icon(icon, color: iconColor, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child:
                  Text(label, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w400)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: value ? const Color(0xFF1A3A1A) : const Color(0xFF1A1A1E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                value ? 'On' : 'Off',
                style: TextStyle(
                  color: value ? const Color(0xFF4ADE80) : const Color(0xFF636366),
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            const SizedBox(width: 6),
            const Icon(Icons.chevron_right_rounded, color: Color(0xFF3A3A3E), size: 20),
          ],
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════
  //  Recordings section
  // ═══════════════════════════════════════════════

  Widget _buildRecordingsSection(List<Wal> pendingWals, List<Wal> syncedWals) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section header
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Row(
            children: [
              const Text('Recordings',
                  style: TextStyle(
                      color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
              if (pendingWals.isNotEmpty) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2A2210),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    '${pendingWals.length} pending',
                    style: const TextStyle(color: Color(0xFFFBBF24), fontSize: 11, fontWeight: FontWeight.w500),
                  ),
                ),
              ],
            ],
          ),
        ),

        // Pending items
        if (pendingWals.isNotEmpty)
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF141416),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFF1F1F23)),
            ),
            child: Column(
              children: [
                for (int i = 0; i < pendingWals.length; i++) ...[
                  _buildRecordingItem(pendingWals[i], isSynced: false),
                  if (i < pendingWals.length - 1)
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16),
                      child: Divider(height: 1, color: Color(0xFF1F1F23)),
                    ),
                ],
              ],
            ),
          ),

        // History
        if (syncedWals.isNotEmpty) ...[
          const SizedBox(height: 12),
          GestureDetector(
            onTap: () => setState(() => _showHistory = !_showHistory),
            child: Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8),
              child: Row(
                children: [
                  Icon(
                    _showHistory ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                    color: const Color(0xFF636366),
                    size: 18,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'Completed (${syncedWals.length})',
                    style: const TextStyle(color: Color(0xFF636366), fontSize: 13, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),
          ),
          if (_showHistory)
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF141416),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFF1F1F23)),
              ),
              child: Column(
                children: [
                  for (int i = 0; i < syncedWals.take(50).length; i++) ...[
                    _buildRecordingItem(syncedWals[i], isSynced: true),
                    if (i < syncedWals.take(50).length - 1)
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 16),
                        child: Divider(height: 1, color: Color(0xFF1F1F23)),
                      ),
                  ],
                ],
              ),
            ),
        ],
      ],
    );
  }

  Widget _buildRecordingItem(Wal wal, {required bool isSynced}) {
    final date = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    final timeStr = dateTimeFormat('h:mm a', date);
    final dateStr = '${_monthName(date.month)} ${date.day}';
    final duration = wal.seconds > 0 ? _formatDuration(wal.seconds) : _formatBytes(wal.storageTotalBytes);

    final (sourceLabel, sourceColor) = _sourceInfo(wal);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      child: Row(
        children: [
          // Status indicator
          if (wal.isSyncing)
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation(Colors.deepPurpleAccent.withValues(alpha: 0.8)),
              ),
            )
          else if (isSynced)
            const Icon(Icons.check_circle_rounded, color: Color(0xFF4ADE80), size: 20)
          else
            Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0xFF3A3A3E), width: 1.5),
              ),
            ),
          const SizedBox(width: 12),

          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$dateStr, $timeStr',
                  style: TextStyle(
                    color: isSynced ? const Color(0xFF8E8E93) : Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w400,
                  ),
                ),
                const SizedBox(height: 2),
                Row(
                  children: [
                    Text(duration, style: const TextStyle(color: Color(0xFF636366), fontSize: 12)),
                    if (wal.isSyncing && wal.syncSpeedKBps != null) ...[
                      const Text(' \u00b7 ', style: TextStyle(color: Color(0xFF636366), fontSize: 12)),
                      Text(
                        '${wal.syncSpeedKBps!.toStringAsFixed(1)} KB/s',
                        style: TextStyle(color: Colors.deepPurpleAccent.withValues(alpha: 0.8), fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),

          // Source badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: sourceColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(100),
            ),
            child: Text(sourceLabel, style: TextStyle(color: sourceColor, fontSize: 11, fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }

  (String, Color) _sourceInfo(Wal wal) {
    switch (wal.storage) {
      case WalStorage.sdcard:
        return ('Device', Colors.deepPurpleAccent);
      case WalStorage.flashPage:
        return ('Limitless', Colors.teal);
      case WalStorage.disk:
        if (wal.originalStorage == WalStorage.sdcard) return ('From device', const Color(0xFF8B5CF6));
        if (wal.originalStorage == WalStorage.flashPage) return ('Limitless', Colors.teal);
        return ('Phone', const Color(0xFF636366));
      default:
        return ('Phone', const Color(0xFF636366));
    }
  }

  // ═══════════════════════════════════════════════
  //  Info bottom sheet
  // ═══════════════════════════════════════════════

  void _showInfoSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF141416),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
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
                    decoration: BoxDecoration(color: const Color(0xFF3A3A3E), borderRadius: BorderRadius.circular(2)),
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  'How syncing works',
                  style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 24),
                _buildInfoStep(
                  number: '1',
                  color: Colors.deepPurpleAccent,
                  title: 'Device stores audio offline',
                  description:
                      'When disconnected from your phone, your device safely stores all recordings in its built-in memory.',
                ),
                const SizedBox(height: 20),
                _buildInfoStep(
                  number: '2',
                  color: const Color(0xFF60A5FA),
                  title: 'Auto-transfer to phone',
                  description:
                      'When your device reconnects, recordings transfer to your phone automatically. No button to press.',
                ),
                const SizedBox(height: 20),
                _buildInfoStep(
                  number: '3',
                  color: const Color(0xFF4ADE80),
                  title: 'Uploaded and transcribed',
                  description:
                      'Your phone uploads recordings to the cloud where they\'re transcribed into conversations.',
                ),
                const SizedBox(height: 24),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1A1A1E),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Tips',
                          style: TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600)),
                      SizedBox(height: 8),
                      Text('\u2022  Keep your phone nearby for faster syncing',
                          style: TextStyle(color: Color(0xFF636366), fontSize: 13, height: 1.6)),
                      Text('\u2022  Stable internet speeds up cloud uploads',
                          style: TextStyle(color: Color(0xFF636366), fontSize: 13, height: 1.6)),
                      Text('\u2022  Recordings sync automatically',
                          style: TextStyle(color: Color(0xFF636366), fontSize: 13, height: 1.6)),
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

  Widget _buildInfoStep({
    required String number,
    required Color color,
    required String title,
    required String description,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: Center(
            child: Text(number, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600)),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500)),
              const SizedBox(height: 4),
              Text(description, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, height: 1.5)),
            ],
          ),
        ),
      ],
    );
  }

  // ═══════════════════════════════════════════════
  //  Helpers
  // ═══════════════════════════════════════════════

  void _confirmCancel(BuildContext context, SyncProvider syncProvider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Stop syncing?',
      message: 'Downloaded files will be uploaded next time you sync.',
      confirmLabel: 'Stop',
      cancelLabel: 'Keep syncing',
    );
    if (confirmed == true) {
      syncProvider.cancelSync();
    }
  }

  String _formatDuration(int seconds) {
    if (seconds < 60) return '${seconds}s';
    final m = seconds ~/ 60;
    final s = seconds % 60;
    if (m < 60) return s > 0 ? '${m}m ${s}s' : '${m}m';
    final h = m ~/ 60;
    final rm = m % 60;
    return rm > 0 ? '${h}h ${rm}m' : '${h}h';
  }

  String _formatBytes(int bytes) {
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
