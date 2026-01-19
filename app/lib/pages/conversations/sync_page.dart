import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/pages/conversations/sync_widgets/wifi_connection_sheet.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'fast_transfer_settings_page.dart';
import 'local_storage_page.dart';
import 'private_cloud_sync_page.dart';
import 'sync_widgets/fast_transfer_suggestion_dialog.dart';
import 'sync_widgets/location_permission_dialog.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
  return Padding(
    padding: const EdgeInsets.only(left: 2, top: 1),
    child: FaIcon(icon, size: size, color: color),
  );
}

class WalListItem extends StatelessWidget {
  final DateTime date;
  final int walIdx;
  final Wal wal;

  const WalListItem({
    super.key,
    required this.wal,
    required this.date,
    required this.walIdx,
  });

  double calculateProgress(DateTime? startedAt, int eta) {
    if (startedAt == null) return 0.0;
    if (eta == 0) return 0.01;

    final elapsed = DateTime.now().difference(startedAt).inSeconds;
    final progress = elapsed / eta;
    return progress.clamp(0.0, 1.0);
  }

  String _formatEta(int seconds) {
    if (seconds < 60) {
      return '${seconds}s';
    } else if (seconds < 3600) {
      final minutes = seconds ~/ 60;
      final secs = seconds % 60;
      return '${minutes}m ${secs}s';
    } else {
      final hours = seconds ~/ 3600;
      final minutes = (seconds % 3600) ~/ 60;
      return '${hours}h ${minutes}m';
    }
  }

  Widget _buildStatusChip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(100),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final hasError = syncProvider.failedWal?.id == wal.id;

        return GestureDetector(
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) => WalItemDetailPage(wal: wal),
              ),
            );
          },
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(16),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Dismissible(
                key: Key(wal.id),
                direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
                confirmDismiss: (direction) {
                  return OmiConfirmDialog.show(
                    context,
                    title: 'Delete Recording',
                    message: 'This cannot be undone.',
                    confirmLabel: 'Delete',
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
                  ServiceManager.instance().wal.getSyncs().deleteWal(wal);
                },
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 36,
                            height: 36,
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2E),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(6),
                              child: Image.asset(
                                DeviceUtils.getDeviceImagePathByModel(wal.deviceModel),
                                width: 24,
                                height: 24,
                              ),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  dateTimeFormat(
                                      'MMM d, h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000)),
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 3),
                                Row(
                                  children: [
                                    Text(
                                      secondsToHumanReadable(wal.seconds),
                                      style: TextStyle(
                                        color: Colors.grey.shade500,
                                        fontSize: 13,
                                      ),
                                    ),
                                    if (wal.storage == WalStorage.sdcard) ...[
                                      const SizedBox(width: 6),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: Colors.deepPurple.withOpacity(0.2),
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                        child: const Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Icon(Icons.sd_card, size: 10, color: Colors.deepPurpleAccent),
                                            SizedBox(width: 3),
                                            Text(
                                              'SD Card',
                                              style: TextStyle(
                                                color: Colors.deepPurpleAccent,
                                                fontSize: 10,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ] else if (wal.originalStorage == WalStorage.sdcard) ...[
                                      const SizedBox(width: 6),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: Colors.deepPurple.withOpacity(0.15),
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Icon(Icons.sd_card, size: 10, color: Colors.deepPurple.shade300),
                                            const SizedBox(width: 3),
                                            Text(
                                              'From SD',
                                              style: TextStyle(
                                                color: Colors.deepPurple.shade300,
                                                fontSize: 10,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ] else if (wal.originalStorage == WalStorage.flashPage) ...[
                                      const SizedBox(width: 6),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: Colors.teal.withValues(alpha: 0.15),
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Icon(Icons.memory, size: 10, color: Colors.teal.shade300),
                                            const SizedBox(width: 3),
                                            Text(
                                              'Limitless',
                                              style: TextStyle(
                                                color: Colors.teal.shade300,
                                                fontSize: 10,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ],
                            ),
                          ),
                          if (wal.isSyncing)
                            _buildStatusChip(
                              wal.syncMethod == SyncMethod.wifi ? 'Fast Transfer' : 'Syncing',
                              wal.syncMethod == SyncMethod.wifi ? Colors.blue : Colors.orange,
                            )
                          else if (hasError)
                            _buildStatusChip('Failed', Colors.red)
                          else if (wal.status == WalStatus.miss)
                            _buildFaIcon(FontAwesomeIcons.circleExclamation, size: 16),
                        ],
                      ),
                      if (wal.isSyncing &&
                          wal.status != WalStatus.synced &&
                          wal.syncStartedAt != null &&
                          wal.storage != WalStorage.flashPage) ...[
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(2),
                                child: LinearProgressIndicator(
                                  value: calculateProgress(wal.syncStartedAt, wal.syncEtaSeconds ?? 0),
                                  backgroundColor: const Color(0xFF3C3C43),
                                  color: wal.syncMethod == SyncMethod.wifi ? Colors.blue : Colors.orange,
                                  minHeight: 3,
                                ),
                              ),
                            ),
                            if (wal.syncSpeedKBps != null && wal.syncSpeedKBps! > 0) ...[
                              const SizedBox(width: 12),
                              Text(
                                '${wal.syncSpeedKBps!.toStringAsFixed(1)} KB/s',
                                style: TextStyle(
                                  color: Colors.grey.shade500,
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ],
                        ),
                        if (wal.syncEtaSeconds != null && wal.syncEtaSeconds! > 0) ...[
                          const SizedBox(height: 4),
                          Text(
                            'ETA: ${_formatEta(wal.syncEtaSeconds!)}',
                            style: TextStyle(
                              color: Colors.grey.shade600,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> with TickerProviderStateMixin {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SyncProvider>().refreshWals();
    });
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
      child: Text(
        title,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildSettingsItem({
    required IconData icon,
    required String title,
    Widget? trailing,
    VoidCallback? onTap,
    bool showChevron = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            SizedBox(
              width: 24,
              height: 24,
              child: _buildFaIcon(icon),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            if (trailing != null) trailing,
            if (showChevron) ...[
              const SizedBox(width: 8),
              const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSettingsCard({required bool showTransferMethod}) {
    final isPhoneStorageOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    final preferredSyncMethod = SharedPreferencesUtil().preferredSyncMethod;
    final isFastTransfer = preferredSyncMethod == 'wifi';

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          if (showTransferMethod) ...[
            _buildSettingsItem(
              icon: FontAwesomeIcons.bolt,
              title: 'Transfer Method',
              trailing: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: isFastTransfer ? Colors.blue.withOpacity(0.2) : const Color(0xFF2A2A2E),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(
                  isFastTransfer ? 'Fast' : 'BLE',
                  style: TextStyle(
                    color: isFastTransfer ? Colors.blue : Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              showChevron: true,
              onTap: () {
                Navigator.of(context)
                    .push(
                      MaterialPageRoute(builder: (context) => const FastTransferSettingsPage()),
                    )
                    .then((_) => setState(() {}));
              },
            ),
            const Divider(height: 1, color: Color(0xFF3C3C43)),
          ],
          _buildSettingsItem(
            icon: FontAwesomeIcons.mobile,
            title: 'Store Audio on Phone',
            trailing: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: isPhoneStorageOn ? Colors.green.withOpacity(0.2) : const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                isPhoneStorageOn ? 'On' : 'Off',
                style: TextStyle(
                  color: isPhoneStorageOn ? Colors.green : Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            showChevron: true,
            onTap: () {
              Navigator.of(context)
                  .push(
                    MaterialPageRoute(builder: (context) => const LocalStoragePage()),
                  )
                  .then((_) => setState(() {}));
            },
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          Consumer<UserProvider>(
            builder: (context, userProvider, child) {
              final isCloudOn = userProvider.privateCloudSyncEnabled;
              return _buildSettingsItem(
                icon: FontAwesomeIcons.cloud,
                title: 'Store Audio on Cloud',
                trailing: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: isCloudOn ? Colors.green.withOpacity(0.2) : const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    isCloudOn ? 'On' : 'Off',
                    style: TextStyle(
                      color: isCloudOn ? Colors.green : Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                showChevron: true,
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (context) => const PrivateCloudSyncPage()),
                  );
                },
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChips(WalStats? stats) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final phoneCount = stats?.phoneFiles ?? 0;
        final sdCardRelatedCount = stats?.sdcardRelatedFiles ?? 0; // On SD card + from SD card
        final flashPageRelatedCount = stats?.flashPageRelatedFiles ?? 0; // On flash page + from flash page
        final totalCount = stats?.totalFiles ?? 0;

        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          physics: const BouncingScrollPhysics(),
          child: Row(
            children: [
              _buildChip(
                  'All', totalCount, syncProvider.storageFilter == null, () => syncProvider.clearStorageFilter()),
              const SizedBox(width: 8),
              _buildChip(
                  'Phone',
                  phoneCount,
                  syncProvider.storageFilter == WalStorage.disk || syncProvider.storageFilter == WalStorage.mem,
                  () => syncProvider.setStorageFilter(WalStorage.disk)),
              const SizedBox(width: 8),
              if (sdCardRelatedCount > 0) ...[
                _buildChip('SD Card', sdCardRelatedCount, syncProvider.storageFilter == WalStorage.sdcard,
                    () => syncProvider.setStorageFilter(WalStorage.sdcard)),
                const SizedBox(width: 8),
              ],
              if (flashPageRelatedCount > 0)
                _buildChip('Limitless', flashPageRelatedCount, syncProvider.storageFilter == WalStorage.flashPage,
                    () => syncProvider.setStorageFilter(WalStorage.flashPage)),
            ],
          ),
        );
      },
    );
  }

  Widget _buildChip(String label, int count, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white.withOpacity(0.12) : const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(100),
          border: isSelected ? Border.all(color: Colors.white.withOpacity(0.3), width: 1) : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.grey.shade400,
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: isSelected ? Colors.white.withOpacity(0.2) : const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  color: isSelected ? Colors.white : Colors.grey.shade500,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showCancelSyncDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Cancel Sync',
      message: 'Data already downloaded will be saved. You can resume later.',
      confirmLabel: 'Cancel Sync',
      confirmColor: Colors.orange,
    );
    if (confirmed == true && context.mounted) {
      provider.cancelSync();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Sync cancelled'), backgroundColor: Colors.orange),
      );
    }
  }

  void _showDeleteProcessedDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Delete Processed Files',
      message: 'This cannot be undone.',
      confirmLabel: 'Delete',
      confirmColor: Colors.red,
    );
    if (confirmed == true && context.mounted) {
      await provider.deleteAllSyncedWals();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Processed files deleted'), backgroundColor: Colors.green),
        );
      }
    }
  }

  void _handleSyncWals(BuildContext context, SyncProvider syncProvider) async {
    final sdCardWals = syncProvider.missingWals.where((wal) => wal.storage == WalStorage.sdcard).toList();

    if (Platform.isIOS && sdCardWals.isNotEmpty) {
      var preferredMethod = SharedPreferencesUtil().preferredSyncMethod;
      final wifiSupported = await ServiceManager.instance().wal.getSyncs().sdcard.isWifiSyncSupported();

      if (preferredMethod == 'ble' && wifiSupported) {
        if (!context.mounted) return;
        final result = await FastTransferSuggestionDialog.show(context);
        if (result == null) {
          return;
        } else if (result == 'switch') {
          SharedPreferencesUtil().preferredSyncMethod = 'wifi';
          preferredMethod = 'wifi';
          if (context.mounted) {
            setState(() {});
          }
        }
      }

      if (preferredMethod == 'wifi' && wifiSupported) {
        if (!context.mounted) return;
        final hasPermission = await LocationPermissionHelper.checkAndRequest(context);
        if (!hasPermission) {
          return;
        }
      }
    }

    if (sdCardWals.isNotEmpty) {
      // Show SD card warning dialog
      if (context.mounted) {
        _showSdCardWarningDialog(context, syncProvider, sdCardWals.length);
      }
    } else {
      syncProvider.syncWals();
    }
  }

  bool _isWifiSyncError(String errorMessage) {
    final lowerMessage = errorMessage.toLowerCase();
    return lowerMessage.contains('wifi') ||
        lowerMessage.contains('hotspot') ||
        lowerMessage.contains('ssid') ||
        lowerMessage.contains('password') ||
        lowerMessage.contains('tcp');
  }

  String _formatErrorMessage(String errorMessage) {
    // Clean up exception prefixes
    if (errorMessage.startsWith('WifiSyncException: ')) {
      errorMessage = errorMessage.substring('WifiSyncException: '.length);
    }
    if (errorMessage.startsWith('Exception: ')) {
      errorMessage = errorMessage.substring('Exception: '.length);
    }

    final lowerMessage = errorMessage.toLowerCase();

    // Map known error patterns to user-friendly messages
    if (lowerMessage.contains('internal error') ||
        lowerMessage.contains('invalidpacketlength') ||
        lowerMessage.contains('packet length')) {
      return 'Failed to enable WiFi on device. Please try again.';
    }
    if (lowerMessage.contains('does not support wifi')) {
      return 'Your device does not support Fast Transfer. Use Bluetooth instead.';
    }
    if (errorMessage.contains('Hotspot name must be') || errorMessage.contains('Password must be')) {
      return errorMessage;
    }
    if (lowerMessage.contains('hotspot') && lowerMessage.contains('enable')) {
      return 'Please enable your phone\'s hotspot and try again.';
    }
    if (lowerMessage.contains('tcp server') || lowerMessage.contains('network server')) {
      return 'Failed to start transfer. Please try again.';
    }
    if (lowerMessage.contains('timeout') || lowerMessage.contains('did not respond')) {
      return 'Device did not respond. Please try again.';
    }
    if (lowerMessage.contains('credentials')) {
      return 'Invalid WiFi credentials. Check your hotspot settings.';
    }
    if (lowerMessage.contains('connection') && lowerMessage.contains('fail')) {
      return 'WiFi connection failed. Please try again.';
    }
    if (lowerMessage.contains('wifi') && lowerMessage.contains('fail')) {
      return 'WiFi connection failed. Please try again.';
    }

    return errorMessage;
  }

  void _showSdCardWarningDialog(BuildContext context, SyncProvider syncProvider, int sdCardCount) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Row(
          children: [
            _buildFaIcon(FontAwesomeIcons.sdCard, size: 20, color: Colors.deepPurpleAccent),
            const SizedBox(width: 12),
            const Text('SD Card Processing', style: TextStyle(color: Colors.white, fontSize: 18)),
          ],
        ),
        content: Text(
          'Processing $sdCardCount recording${sdCardCount > 1 ? 's' : ''}. Files will be removed from SD card after.',
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text('Cancel', style: TextStyle(color: Colors.grey.shade500))),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              _startSyncWithWifiSheet(context, syncProvider);
            },
            child: const Text('Process', style: TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  /// Start sync and show WiFi connection sheet if using WiFi sync
  Future<void> _startSyncWithWifiSheet(BuildContext context, SyncProvider syncProvider) async {
    final preferredMethod = SharedPreferencesUtil().preferredSyncMethod;
    final wifiSupported = await ServiceManager.instance().wal.getSyncs().sdcard.isWifiSyncSupported();
    final hasSDCardWals = syncProvider.missingWals.any((w) => w.storage == WalStorage.sdcard);

    if (preferredMethod == 'wifi' && wifiSupported && hasSDCardWals && context.mounted) {
      WifiConnectionListenerBridge? listener;

      final controller = await WifiConnectionSheet.show(
        context,
        deviceName: 'Omi',
        onCancel: () {
          syncProvider.cancelSync();
        },
        onRetry: () {
          if (listener != null) {
            syncProvider.syncWals(connectionListener: listener);
          }
        },
      );

      listener = WifiConnectionListenerBridge(controller);
      syncProvider.syncWals(connectionListener: listener);
    } else {
      syncProvider.syncWals();
    }
  }

  Widget _buildProcessCard(SyncProvider syncProvider) {
    // Error state
    if (syncProvider.syncError != null && syncProvider.failedWal == null) {
      final errorMessage = syncProvider.syncError!;
      final isWifiError = _isWifiSyncError(errorMessage);

      return Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  SizedBox(
                    width: 24,
                    height: 24,
                    child: _buildFaIcon(
                      isWifiError ? FontAwesomeIcons.wifi : FontAwesomeIcons.circleExclamation,
                      color: Colors.red,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isWifiError ? 'WiFi Sync Failed' : 'Processing Failed',
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _formatErrorMessage(errorMessage),
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: GestureDetector(
                      onTap: () => syncProvider.retrySync(),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2A2A2E),
                          borderRadius: BorderRadius.circular(100),
                        ),
                        child: const Center(
                          child: Text(
                            'Retry',
                            style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }

    // Syncing state
    if (syncProvider.isSyncing) {
      final progress =
          syncProvider.walBasedProgress > 0 ? syncProvider.walBasedProgress : syncProvider.walsSyncedProgress;
      final speedKBps = syncProvider.syncSpeedKBps;
      final isSdCardSyncing = syncProvider.isSdCardSyncing;

      // Get sync method from the currently syncing WAL
      final syncingWal = syncProvider.allWals.where((w) => w.isSyncing).firstOrNull;
      final isWifiSync = syncingWal?.syncMethod == SyncMethod.wifi;

      return Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: isWifiSync ? Colors.blue.withOpacity(0.2) : Colors.deepPurple.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      isWifiSync ? Icons.bolt : Icons.bluetooth,
                      color: isWifiSync ? Colors.blue : Colors.deepPurpleAccent,
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                isSdCardSyncing
                                    ? 'Downloading from SD Card'
                                    : 'Processing ${syncProvider.processedWalsCount}/${syncProvider.initialMissingWalsCount}',
                                style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                        if (speedKBps != null && speedKBps > 0) ...[
                          const SizedBox(height: 4),
                          Text(
                            '${speedKBps.toStringAsFixed(1)} KB/s',
                            style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                          ),
                        ],
                      ],
                    ),
                  ),
                  Text(
                    '${(progress * 100).toInt()}%',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14, fontWeight: FontWeight.w500),
                  ),
                  if (isSdCardSyncing) ...[
                    const SizedBox(width: 12),
                    GestureDetector(
                      onTap: () => _showCancelSyncDialog(context, syncProvider),
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.red.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.close, color: Colors.red, size: 18),
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: progress,
                  backgroundColor: const Color(0xFF3C3C43),
                  color: isWifiSync ? Colors.blue : Colors.deepPurpleAccent,
                  minHeight: 4,
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Completed state
    if (syncProvider.syncCompleted && syncProvider.syncedConversationsPointers.isNotEmpty) {
      return Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: GestureDetector(
          onTap: () => routeToPage(context, const SyncedConversationsPage()),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              children: [
                SizedBox(width: 24, height: 24, child: _buildFaIcon(FontAwesomeIcons.circleCheck, color: Colors.green)),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    '${syncProvider.syncedConversationsPointers.length} conversations created',
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                  ),
                ),
                const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
              ],
            ),
          ),
        ),
      );
    }

    // Default state - show process button
    final totalSecondsToProcess = syncProvider.missingWalsInSeconds;

    if (totalSecondsToProcess == 0) {
      return const SizedBox.shrink();
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: GestureDetector(
        onTap: () {
          if (context.read<ConnectivityProvider>().isConnected) {
            _handleSyncWals(context, syncProvider);
          } else {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('Internet required'),
                backgroundColor: Colors.red.shade700,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            );
          }
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          child: Row(
            children: [
              SizedBox(
                  width: 24, height: 24, child: _buildFaIcon(FontAwesomeIcons.bolt, color: Colors.deepPurpleAccent)),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Process Audio',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 3),
                    Text(
                      secondsToHumanReadable(totalSecondsToProcess),
                      style: const TextStyle(color: Colors.amber, fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.deepPurpleAccent,
                  borderRadius: BorderRadius.circular(100),
                ),
                child: const Text('Start',
                    style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A2E),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Center(child: _buildFaIcon(FontAwesomeIcons.microphone, size: 24)),
          ),
          const SizedBox(height: 20),
          const Text('No Recordings', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Text('Audio from your Omi device will appear here',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 14), textAlign: TextAlign.center),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvoked: (didPop) {
        var provider = Provider.of<SyncProvider>(context, listen: false);
        if (!provider.isSyncing) provider.clearSyncResult();
      },
      child: Consumer<SyncProvider>(builder: (context, syncProvider, child) {
        return Scaffold(
          backgroundColor: const Color(0xFF0D0D0D),
          appBar: AppBar(
            backgroundColor: const Color(0xFF0D0D0D),
            elevation: 0,
            leading: IconButton(
              icon: const Padding(
                padding: EdgeInsets.only(left: 2, top: 1),
                child: FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
              ),
              onPressed: () => Navigator.of(context).pop(),
            ),
            title: const Text('Offline Sync',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
            centerTitle: true,
            actions: [
              PullDownButton(
                itemBuilder: (context) => [
                  PullDownMenuItem(
                    title: 'Delete Processed',
                    iconWidget: _buildFaIcon(FontAwesomeIcons.trash, size: 16, color: Colors.red),
                    isDestructive: true,
                    onTap: () => _showDeleteProcessedDialog(context, syncProvider),
                  ),
                ],
                buttonBuilder: (context, showMenu) => GestureDetector(
                  onTap: () {
                    HapticFeedback.mediumImpact();
                    showMenu();
                  },
                  child: Container(
                    width: 36,
                    height: 36,
                    margin: const EdgeInsets.only(right: 8),
                    decoration: BoxDecoration(
                      color: Colors.grey.withOpacity(0.3),
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: _buildFaIcon(FontAwesomeIcons.ellipsisVertical, size: 16, color: Colors.white),
                    ),
                  ),
                ),
              ),
            ],
          ),
          body: FutureBuilder<WalStats>(
            future: syncProvider.getWalStats(),
            builder: (context, statsSnapshot) {
              return CustomScrollView(
                slivers: [
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SizedBox(height: 16),
                          _buildProcessCard(syncProvider),
                          const SizedBox(height: 16),
                          FutureBuilder<bool>(
                            future: ServiceManager.instance().wal.getSyncs().sdcard.isWifiSyncSupported(),
                            builder: (context, wifiSnapshot) {
                              final wifiSupported = wifiSnapshot.data ?? false;
                              return _buildSettingsCard(showTransferMethod: wifiSupported);
                            },
                          ),
                          const SizedBox(height: 20),
                          _buildSectionHeader('Recordings'),
                          _buildFilterChips(statsSnapshot.data),
                          const SizedBox(height: 16),
                        ],
                      ),
                    ),
                  ),
                  Consumer<SyncProvider>(
                    builder: (context, syncProvider, child) {
                      if (syncProvider.isLoadingWals && syncProvider.allWals.isEmpty) {
                        return const SliverToBoxAdapter(
                          child: Center(
                              child: Padding(
                                  padding: EdgeInsets.all(32), child: CircularProgressIndicator(color: Colors.white))),
                        );
                      }

                      final filteredWals = syncProvider.filteredWals;

                      if (syncProvider.allWals.isEmpty) {
                        return SliverToBoxAdapter(child: _buildEmptyState());
                      }

                      if (filteredWals.isEmpty && syncProvider.storageFilter != null) {
                        return SliverToBoxAdapter(
                          child: Container(
                            margin: const EdgeInsets.all(20),
                            padding: const EdgeInsets.all(32),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1C1C1E),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Column(
                              children: [
                                _buildFaIcon(FontAwesomeIcons.filter, size: 24),
                                const SizedBox(height: 16),
                                const Text('No Recordings',
                                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                                const SizedBox(height: 4),
                                Text('Try a different filter',
                                    style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
                              ],
                            ),
                          ),
                        );
                      }

                      return OptimizedWalsListWidget(wals: filteredWals);
                    },
                  ),
                  const SliverToBoxAdapter(child: SizedBox(height: 100)),
                ],
              );
            },
          ),
        );
      }),
    );
  }
}

Map<DateTime, List<Wal>> _groupWalsByDate(List<Wal> wals) {
  var groupedWals = <DateTime, List<Wal>>{};
  wals.sort((a, b) => b.timerStart.compareTo(a.timerStart));
  for (var wal in wals) {
    var createdAt = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
    var date = DateTime(createdAt.year, createdAt.month, createdAt.day, createdAt.hour);
    if (!groupedWals.containsKey(date)) groupedWals[date] = [];
    groupedWals[date]?.add(wal);
  }
  for (final date in groupedWals.keys) {
    groupedWals[date]?.sort((a, b) => b.timerStart.compareTo(a.timerStart));
  }
  return groupedWals;
}

class OptimizedWalsListWidget extends StatelessWidget {
  final List<Wal> wals;
  const OptimizedWalsListWidget({super.key, required this.wals});

  @override
  Widget build(BuildContext context) {
    final flattenedItems = _createFlattenedItems(wals);

    return SliverList.builder(
      itemCount: flattenedItems.length,
      itemBuilder: (context, index) {
        final item = flattenedItems[index];

        if (item is DateHeaderItem) {
          return Padding(
            padding: EdgeInsets.fromLTRB(20, index == 0 ? 0 : 24, 20, 8),
            child: Text(
              dateTimeFormat('MMM d, h a', item.date),
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w500),
            ),
          );
        } else if (item is WalItem) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
            child: WalListItem(wal: item.wal, walIdx: item.index, date: item.date),
          );
        }
        return const SizedBox.shrink();
      },
    );
  }

  List<ListItem> _createFlattenedItems(List<Wal> wals) {
    final groupedWals = _groupWalsByDate(wals);
    final List<ListItem> items = [];
    for (final entry in groupedWals.entries) {
      items.add(DateHeaderItem(entry.key));
      for (int i = 0; i < entry.value.length; i++) {
        items.add(WalItem(entry.value[i], i, entry.key));
      }
    }
    return items;
  }
}

abstract class ListItem {}

class DateHeaderItem extends ListItem {
  final DateTime date;
  DateHeaderItem(this.date);
}

class WalItem extends ListItem {
  final Wal wal;
  final int index;
  final DateTime date;
  WalItem(this.wal, this.index, this.date);
}
