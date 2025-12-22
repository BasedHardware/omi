import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:provider/provider.dart';

import 'private_cloud_sync_page.dart';
import 'synced_conversations_page.dart';
import 'wal_item_detail/wal_item_detail_page.dart';

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

    final elapsed = DateTime.now().difference(startedAt!).inSeconds;
    final progress = elapsed / eta;
    return progress.clamp(0.0, 1.0);
  }

  Widget _buildStatusChip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(8),
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

  void _showSdCardInfoDialog(BuildContext context) {
    final theme = Theme.of(context);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            const Icon(Icons.info_outline, color: Colors.amber, size: 24),
            const SizedBox(width: 12),
            Text('SD Card Audio', style: theme.textTheme.titleLarge),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'This audio file is stored on your device\'s SD card.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            Text(
              'You can process the file but cannot play or share it directly from the SD card.',
              style: theme.textTheme.bodyMedium?.copyWith(color: Colors.white70),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('Got it', style: TextStyle(color: theme.colorScheme.secondary, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final hasError = syncProvider.failedWal?.id == wal.id;

        return GestureDetector(
          onTap: wal.storage == WalStorage.sdcard
              ? () {
                  _showSdCardInfoDialog(context);
                }
              : () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => WalItemDetailPage(wal: wal),
                    ),
                  );
                },
          child: Padding(
            padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
            child: Container(
              width: double.maxFinite,
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(16.0),
              ),
              child: Stack(
                children: [
                  Opacity(
                    opacity: wal.storage == WalStorage.sdcard ? 0.8 : 1.0,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(16.0),
                      child: Dismissible(
                        key: Key(wal.id),
                        direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
                        confirmDismiss: (direction) {
                          return OmiConfirmDialog.show(
                            context,
                            title: 'Confirm Deletion',
                            message: 'Are you sure you want to delete this audio file? This action cannot be undone.',
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
                          padding: const EdgeInsets.all(16.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  // Device image
                                  Container(
                                    width: 32,
                                    height: 32,
                                    decoration: BoxDecoration(
                                      color: Colors.white.withOpacity(0.7),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Padding(
                                      padding: const EdgeInsets.all(4.0),
                                      child: Image.asset(
                                        DeviceUtils.getDeviceImagePathByModel(wal.deviceModel),
                                        width: 24,
                                        height: 24,
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  // Main content
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          dateTimeFormat('MMM dd, yyyy h:mm a',
                                              DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000)),
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          wal.storage == WalStorage.flashPage
                                              ? '${wal.deviceModel ?? "Limitless"} • Offline Recording'
                                              : '${secondsToHumanReadable(wal.seconds)} • ${wal.deviceModel ?? "Omi Device"}${wal.storage == WalStorage.sdcard ? " • SD Card" : ""}',
                                          style: TextStyle(
                                            color: Colors.grey.shade400,
                                            fontSize: 14,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  // Simplified status indicator
                                  if (wal.isSyncing)
                                    _buildStatusChip('Processing', Colors.orange)
                                  else if (hasError)
                                    _buildStatusChip('Failed', Colors.red)
                                  else if (wal.status == WalStatus.miss)
                                    _buildStatusChip('Not Processed', Colors.grey)
                                ],
                              ),
                              // Progress bar for syncing - only show if actually syncing and not flash page
                              if (wal.isSyncing &&
                                  wal.status != WalStatus.synced &&
                                  wal.syncStartedAt != null &&
                                  wal.storage != WalStorage.flashPage) ...[
                                const SizedBox(height: 8),
                                SizedBox(
                                  height: 2,
                                  child: LinearProgressIndicator(
                                    value: calculateProgress(wal.syncStartedAt, wal.syncEtaSeconds ?? 0),
                                    backgroundColor: Colors.grey[800],
                                    color: Colors.white70,
                                  ),
                                ),
                              ],
                              // Error message
                              if (hasError && syncProvider.syncError != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  syncProvider.syncError!,
                                  style: TextStyle(color: Colors.grey.shade400, fontSize: 11),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class DateTimeListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;

  const DateTimeListItem({super.key, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(16, isFirst ? 0 : 20, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            dateTimeFormat('MMM dd hh:00 a', date),
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Container(
              height: 1,
              color: Color(0xFF35343B),
            ),
          )
        ],
      ),
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
      final syncProvider = context.read<SyncProvider>();
      syncProvider.refreshWals();

      // Don't clear sync state on page init - preserve existing state
      // This ensures that if user navigates away and back, they see the current sync status
    });
  }

  Widget _buildStatItem(String label, String value) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          value,
          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildStorageControlCard() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Storage Settings',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Complete Archive',
                      style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      SharedPreferencesUtil().unlimitedLocalStorageEnabled
                          ? 'Create a complete personal archive of all your recordings'
                          : 'Save phone\'s storage space by only keeping failed uploads',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              CupertinoSwitch(
                value: SharedPreferencesUtil().unlimitedLocalStorageEnabled,
                onChanged: (value) {
                  if (value) {
                    _showConsentDialog(context, () {
                      SharedPreferencesUtil().unlimitedLocalStorageEnabled = value;
                      context.read<SyncProvider>().refreshWals();
                    });
                  } else {
                    SharedPreferencesUtil().unlimitedLocalStorageEnabled = value;
                    context.read<SyncProvider>().refreshWals();
                  }
                },
                activeColor: Colors.deepPurpleAccent,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Divider(color: Colors.grey.withOpacity(0.2)),
          const SizedBox(height: 16),
          Consumer<UserProvider>(
            builder: (context, userProvider, child) {
              final isEnabled = userProvider.privateCloudSyncEnabled;
              return InkWell(
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const PrivateCloudSyncPage(),
                    ),
                  );
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8.0),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Private Cloud Sync',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Store real-time recordings in the private cloud',
                              style: TextStyle(
                                color: Colors.grey.shade400,
                                fontSize: 14,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        isEnabled ? 'On' : 'Off',
                        style: TextStyle(
                          color: Colors.grey.shade500,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Icon(Icons.arrow_forward_ios, color: Colors.grey.shade400, size: 18),
                    ],
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildStorageFilterChips() {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.filter_list, color: Colors.white70, size: 16),
                  SizedBox(width: 8),
                  Text(
                    'Filter:',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                child: Row(
                  children: [
                    _buildFilterChip(
                      label: 'All Recordings',
                      isSelected: syncProvider.storageFilter == null,
                      onTap: () => syncProvider.clearStorageFilter(),
                    ),
                    const SizedBox(width: 8),
                    _buildFilterChip(
                      label: 'Phone Storage',
                      isSelected:
                          syncProvider.storageFilter == WalStorage.disk || syncProvider.storageFilter == WalStorage.mem,
                      onTap: () => syncProvider.setStorageFilter(WalStorage.disk),
                    ),
                    const SizedBox(width: 8),
                    _buildFilterChip(
                      label: 'SD Card',
                      isSelected: syncProvider.storageFilter == WalStorage.sdcard,
                      onTap: () => syncProvider.setStorageFilter(WalStorage.sdcard),
                    ),
                    const SizedBox(width: 8),
                    _buildFilterChip(
                      label: 'Limitless',
                      isSelected: syncProvider.storageFilter == WalStorage.flashPage,
                      onTap: () => syncProvider.setStorageFilter(WalStorage.flashPage),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFilterChip({
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white.withOpacity(0.1) : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.grey.shade400,
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
      ),
    );
  }

  void _showConsentDialog(BuildContext context, VoidCallback onConfirm) {
    bool consentConfirmed = false;

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          return AlertDialog(
            backgroundColor: const Color(0xFF1A1A1A),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Row(
              children: [
                Icon(Icons.privacy_tip, color: Colors.orange, size: 24),
                SizedBox(width: 12),
                Text('Privacy & Consent', style: TextStyle(color: Colors.white)),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'You\'re switching to Complete Archive Mode, which will keep all your audio recordings on this device.',
                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.privacy_tip, color: Colors.grey.shade400, size: 16),
                          const SizedBox(width: 6),
                          Text(
                            'Privacy Notice',
                            style: TextStyle(color: Colors.grey.shade300, fontWeight: FontWeight.w600, fontSize: 14),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Your recordings may capture other people\'s voices. Please ensure you have consent from all participants before recording.',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Checkbox(
                      value: consentConfirmed,
                      onChanged: (value) {
                        setState(() {
                          consentConfirmed = value ?? false;
                        });
                      },
                      activeColor: Colors.deepPurple,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'I have consent from all participants in my recordings',
                        style: TextStyle(color: Colors.white70, fontSize: 14),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
              ),
              TextButton(
                onPressed: consentConfirmed
                    ? () {
                        Navigator.of(context).pop();
                        onConfirm();
                      }
                    : null,
                child: Text(
                  'Enable Storage',
                  style: TextStyle(
                    color: consentConfirmed ? Colors.deepPurple : Colors.grey,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _showDeleteProcessedDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Delete All Processed Files',
      message: 'This will permanently delete all processed audio files from your phone. This action cannot be undone.',
      confirmLabel: 'Delete',
      confirmColor: Colors.red,
    );

    if (confirmed == true && context.mounted) {
      await provider.deleteAllSyncedWals();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('All processed audio files have been deleted'),
            backgroundColor: Colors.green,
          ),
        );
      }
    }
  }

  void _handleSyncWals(BuildContext context, SyncProvider syncProvider) {
    // Check if there are any SD card WALs in the missing list
    final missingWals = syncProvider.missingWals;
    final sdCardWals = missingWals.where((wal) => wal.storage == WalStorage.sdcard).toList();

    if (sdCardWals.isNotEmpty) {
      _showSdCardWarningDialog(context, syncProvider, sdCardWals.length);
    } else {
      syncProvider.syncWals();
    }
  }

  void _showSdCardWarningDialog(BuildContext context, SyncProvider syncProvider, int sdCardCount) {
    final theme = Theme.of(context);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            Icon(Icons.sd_card, color: theme.colorScheme.secondary, size: 24),
            const SizedBox(width: 12),
            Text('SD Card Processing', style: theme.textTheme.titleLarge),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Ready to process $sdCardCount recording${sdCardCount > 1 ? 's' : ''} from your SD card into conversations.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'After processing, the original files will be removed from your SD card to free up storage space.',
                style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).pop();
              syncProvider.syncWals();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.secondary,
              foregroundColor: Colors.white,
            ),
            child: const Text('Process'),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    super.dispose();
  }

  Widget _buildSummaryCard(SyncProvider syncProvider) {
    if (syncProvider.syncError != null && syncProvider.failedWal == null) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error_outline, color: Colors.red, size: 24),
                SizedBox(width: 12),
                Text(
                  'Something Went Wrong',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              syncProvider.syncError!,
              style: const TextStyle(color: Colors.white70, fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () => syncProvider.retrySync(),
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text(
                  'Try Again',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.grey.shade700,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    if (syncProvider.isSyncing) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.orange),
                ),
                SizedBox(width: 12),
                Text(
                  'Creating Your Conversations...',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            LinearProgressIndicator(
              value:
                  syncProvider.walBasedProgress > 0 ? syncProvider.walBasedProgress : syncProvider.walsSyncedProgress,
              backgroundColor: Colors.grey[800],
              color: Colors.white70,
              minHeight: 4,
            ),
            const SizedBox(height: 8),
            Text(
              syncProvider.walBasedProgress > 0
                  ? '${(syncProvider.walBasedProgress * 100).toInt()}% complete (${syncProvider.processedWalsCount}/${syncProvider.initialMissingWalsCount} recordings)'
                  : 'Processing...',
              style: const TextStyle(color: Colors.white70, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            const Text(
              'Please keep the app open while we work on your recordings.',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
        ),
      );
    }

    if (syncProvider.syncCompleted && syncProvider.syncedConversationsPointers.isNotEmpty) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.check_circle, color: Colors.green, size: 24),
                SizedBox(width: 12),
                Text(
                  'All Done!',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              'Successfully created ${syncProvider.syncedConversationsPointers.length} conversations from your recordings.',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {
                  routeToPage(context, const SyncedConversationsPage());
                },
                icon: const Icon(Icons.visibility, size: 18),
                label: const Text(
                  'View Your New Conversations',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.secondary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    return FutureBuilder<WalStats>(
      future: syncProvider.getWalStats(),
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const SizedBox(height: 24);
        }
        final stats = snapshot.data!;
        final totalSecondsToProcess = syncProvider.missingWalsInSeconds;

        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            children: [
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.schedule, color: Colors.white70, size: 24),
                  SizedBox(width: 8),
                  Text(
                    secondsToHumanReadable(totalSecondsToProcess),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      letterSpacing: -0.5,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                totalSecondsToProcess > 0
                    ? '${stats.missedFiles} audio recording${stats.missedFiles != 1 ? 's' : ''} ready to convert into readable conversations'
                    : 'All your audio recordings have been processed into conversations',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              Divider(color: Colors.grey.withOpacity(0.2)),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _buildStatItem('Total Files', '${stats.totalFiles}'),
                  _buildStatItem('Total Size', stats.totalSizeFormatted),
                  _buildStatItem('On Phone', '${stats.phoneFiles}'),
                  if (stats.sdcardFiles > 0) _buildStatItem('On SD Card', '${stats.sdcardFiles}'),
                  if (stats.limitlessFiles > 0) _buildStatItem('Limitless', '${stats.limitlessFiles}'),
                ],
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: totalSecondsToProcess == 0
                      ? null
                      : () {
                          if (context.read<ConnectivityProvider>().isConnected) {
                            _handleSyncWals(context, syncProvider);
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: const Row(
                                  children: [
                                    Icon(Icons.wifi_off, color: Colors.white),
                                    SizedBox(width: 8),
                                    Text('Internet connection required for AI processing'),
                                  ],
                                ),
                                backgroundColor: Colors.red.shade700,
                                behavior: SnackBarBehavior.floating,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                            );
                          }
                        },
                  icon: const Icon(Icons.cloud_upload, size: 20),
                  label: Text(
                    totalSecondsToProcess > 0 ? 'Process Audio' : 'All Audio Processed',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor:
                        totalSecondsToProcess > 0 ? Theme.of(context).colorScheme.secondary : Colors.grey.shade600,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 0,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvoked: (didPop) {
        // Only clear sync result if sync is completed or has error
        // Don't clear if sync is in progress to preserve state
        var provider = Provider.of<SyncProvider>(context, listen: false);
        if (!provider.isSyncing) {
          provider.clearSyncResult();
        }
      },
      child: Consumer<SyncProvider>(builder: (context, syncProvider, child) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Storage'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            actions: [
              FutureBuilder<WalStats>(
                future: syncProvider.getWalStats(),
                builder: (context, snapshot) {
                  return PopupMenuButton<String>(
                    onSelected: (value) {
                      if (value == 'delete_all') {
                        _showDeleteProcessedDialog(context, syncProvider);
                      }
                    },
                    itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
                      const PopupMenuItem<String>(
                        value: 'delete_all',
                        child: ListTile(
                          leading: Icon(Icons.delete_sweep),
                          title: Text('Delete All Processed Files'),
                        ),
                      ),
                    ],
                  );
                  return const SizedBox.shrink();
                },
              ),
            ],
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Column(
                  children: [
                    _buildStorageControlCard(),
                    _buildSummaryCard(syncProvider),
                    _buildStorageFilterChips(),
                    SizedBox(height: 16),
                  ],
                ),
              ),
              Consumer<SyncProvider>(
                builder: (context, syncProvider, child) {
                  if (syncProvider.isLoadingWals && syncProvider.allWals.isEmpty) {
                    return const SliverToBoxAdapter(
                      child: Center(
                        child: Padding(
                          padding: EdgeInsets.all(32.0),
                          child: CircularProgressIndicator(color: Colors.white),
                        ),
                      ),
                    );
                  }

                  final allWals = syncProvider.allWals;
                  final filteredWals = syncProvider.filteredWals;

                  if (allWals.isEmpty) {
                    return SliverToBoxAdapter(
                      child: Container(
                        margin: const EdgeInsets.all(32.0),
                        padding: const EdgeInsets.all(32.0),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1F25),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: Colors.deepPurple.withOpacity(0.1),
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(
                                Icons.mic_none,
                                color: Colors.deepPurple,
                                size: 48,
                              ),
                            ),
                            const SizedBox(height: 16),
                            const Text(
                              'No Audio Files Yet',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              'Your Omi device will automatically save audio recordings here. Once you have recordings, you can process them into readable conversations.',
                              style: TextStyle(color: Colors.grey, fontSize: 14),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 12),
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.grey.withOpacity(0.15),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Row(
                                children: [
                                  Icon(Icons.info_outline, color: Colors.grey.shade400, size: 16),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      'Phone microphone recordings are processed instantly and don\'t appear here.',
                                      style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  if (filteredWals.isEmpty && syncProvider.storageFilter != null) {
                    return SliverToBoxAdapter(
                      child: Container(
                        margin: const EdgeInsets.all(32.0),
                        padding: const EdgeInsets.all(32.0),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1F25),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: Colors.grey.withOpacity(0.1),
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(
                                Icons.filter_list_off,
                                color: Colors.grey,
                                size: 48,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              syncProvider.storageFilter == WalStorage.sdcard
                                  ? 'No SD Card Recordings'
                                  : 'No Phone Storage Recordings',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              syncProvider.storageFilter == WalStorage.sdcard
                                  ? 'No audio files found on your device\'s SD card. Make sure your Omi device has recorded audio to its SD card.'
                                  : 'No audio files found in phone storage. Audio gets stored here when your Omi device transfers recordings to your phone.',
                              style: const TextStyle(color: Colors.grey, fontSize: 14),
                              textAlign: TextAlign.center,
                            ),
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
    if (!groupedWals.containsKey(date)) {
      groupedWals[date] = [];
    }
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
    // Flatten the grouped structure for better performance
    final flattenedItems = _createFlattenedItems(wals);

    return SliverList.builder(
      itemCount: flattenedItems.length,
      itemBuilder: (context, index) {
        final item = flattenedItems[index];

        if (item is DateHeaderItem) {
          return Padding(
            padding: EdgeInsets.fromLTRB(16, index == 0 ? 0 : 20, 16, 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Text(
                  dateTimeFormat('MMM dd hh:00 a', item.date),
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Container(
                    height: 1,
                    color: Color(0xFF35343B),
                  ),
                )
              ],
            ),
          );
        } else if (item is WalItem) {
          return Padding(
            padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
            child: WalListItem(
              wal: item.wal,
              walIdx: item.index,
              date: item.date,
            ),
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

// Helper classes for flattened list
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
