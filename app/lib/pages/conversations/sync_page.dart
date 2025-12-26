import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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
import 'package:pull_down_button/pull_down_button.dart';

import 'local_storage_page.dart';
import 'private_cloud_sync_page.dart';
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
          onTap: wal.storage == WalStorage.sdcard
              ? null
              : () {
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
                                Text(
                                  '${secondsToHumanReadable(wal.seconds)}${wal.storage == WalStorage.sdcard ? " • SD Card" : ""}',
                                  style: TextStyle(
                                    color: Colors.grey.shade500,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (wal.isSyncing)
                            _buildStatusChip('Processing', Colors.orange)
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
                        ClipRRect(
                          borderRadius: BorderRadius.circular(2),
                          child: LinearProgressIndicator(
                            value: calculateProgress(wal.syncStartedAt, wal.syncEtaSeconds ?? 0),
                            backgroundColor: const Color(0xFF3C3C43),
                            color: Colors.white70,
                            minHeight: 3,
                          ),
                        ),
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

  Widget _buildSettingsCard() {
    final isPhoneStorageOn = SharedPreferencesUtil().unlimitedLocalStorageEnabled;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
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
        final sdCardCount = stats?.sdcardFiles ?? 0;
        final limitlessCount = stats?.limitlessFiles ?? 0;
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
              if (sdCardCount > 0) ...[
                _buildChip('SD Card', sdCardCount, syncProvider.storageFilter == WalStorage.sdcard,
                    () => syncProvider.setStorageFilter(WalStorage.sdcard)),
                const SizedBox(width: 8),
              ],
              if (limitlessCount > 0)
                _buildChip('Limitless', limitlessCount, syncProvider.storageFilter == WalStorage.flashPage,
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

  void _handleSyncWals(BuildContext context, SyncProvider syncProvider) {
    final sdCardWals = syncProvider.missingWals.where((wal) => wal.storage == WalStorage.sdcard).toList();
    if (sdCardWals.isNotEmpty) {
      _showSdCardWarningDialog(context, syncProvider, sdCardWals.length);
    } else {
      syncProvider.syncWals();
    }
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
              syncProvider.syncWals();
            },
            child: const Text('Process', style: TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  Widget _buildProcessCard(SyncProvider syncProvider) {
    // Error state
    if (syncProvider.syncError != null && syncProvider.failedWal == null) {
      return Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              SizedBox(
                  width: 24, height: 24, child: _buildFaIcon(FontAwesomeIcons.circleExclamation, color: Colors.red)),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Processing Failed',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 2),
                    Text(syncProvider.syncError!,
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: () => syncProvider.retrySync(),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: const Text('Retry',
                      style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500)),
                ),
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
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Text(
                      'Processing ${syncProvider.processedWalsCount}/${syncProvider.initialMissingWalsCount}',
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                  ),
                  Text(
                    '${(progress * 100).toInt()}%',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: progress,
                  backgroundColor: const Color(0xFF3C3C43),
                  color: Colors.white,
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
              icon: Padding(
                padding: const EdgeInsets.only(left: 2, top: 1),
                child: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
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
                          _buildSettingsCard(),
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
