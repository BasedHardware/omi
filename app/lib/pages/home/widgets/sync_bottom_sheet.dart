import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:provider/provider.dart';

class SyncBottomSheet extends StatelessWidget {
  const SyncBottomSheet({super.key});

  static void show(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => const SyncBottomSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<DeviceProvider, SyncProvider>(
      builder: (context, deviceProvider, syncProvider, child) {
        final device = deviceProvider.pairedDevice;
        final isLimitless = device?.type == DeviceType.limitless;
        final isConnected = deviceProvider.isConnected;

        final pendingFlashPages =
            syncProvider.allWals.where((w) => w.storage == WalStorage.flashPage && w.status == WalStatus.miss).toList();

        final isSyncing = syncProvider.isSyncing;
        final progress = syncProvider.walsSyncedProgress;
        final hasPendingData = pendingFlashPages.isNotEmpty;

        // Check for orphaned files from previous failed syncs
        final flashPageSync = ServiceManager.instance().wal.getSyncs().flashPage;
        final hasOrphanedFiles = flashPageSync.hasOrphanedFiles;
        final orphanedCount = flashPageSync.orphanedFilesCount;
        final isUploadingOrphans = flashPageSync.isUploadingOrphans;

        // Calculate time ago for pending data
        String timeAgo = '';
        if (hasPendingData && pendingFlashPages.isNotEmpty) {
          final oldestWal = pendingFlashPages.reduce((a, b) => a.timerStart < b.timerStart ? a : b);
          final minutesAgo = ((DateTime.now().millisecondsSinceEpoch ~/ 1000) - oldestWal.timerStart) ~/ 60;
          if (minutesAgo < 60) {
            timeAgo = '$minutesAgo minutes ago';
          } else if (minutesAgo < 1440) {
            timeAgo = '${minutesAgo ~/ 60} hours ago';
          } else {
            timeAgo = '${minutesAgo ~/ 1440} days ago';
          }
        }

        return Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1A1A1F),
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Handle bar
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 28),

              // Icon
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      Colors.deepPurple.shade400,
                      Colors.purple.shade600,
                    ],
                  ),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.deepPurple.withOpacity(0.3),
                      blurRadius: 20,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: Icon(
                  isSyncing ? Icons.sync_rounded : (hasPendingData ? Icons.graphic_eq_rounded : Icons.check_rounded),
                  color: Colors.white,
                  size: 36,
                ),
              ),
              const SizedBox(height: 24),

              // Title
              Text(
                isSyncing ? 'Catching Up' : (hasPendingData ? 'Recordings Available' : 'All Synced'),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),

              // Description
              if (isSyncing) ...[
                RichText(
                  textAlign: TextAlign.center,
                  text: TextSpan(
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 16,
                      height: 1.4,
                    ),
                    children: [
                      const TextSpan(text: 'Processing audio and generating summaries from '),
                      TextSpan(
                        text: timeAgo.isNotEmpty ? timeAgo : 'earlier',
                        style: const TextStyle(color: Colors.deepPurpleAccent),
                      ),
                      const TextSpan(text: '.'),
                    ],
                  ),
                ),
              ] else if (hasPendingData) ...[
                RichText(
                  textAlign: TextAlign.center,
                  text: TextSpan(
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 16,
                      height: 1.4,
                    ),
                    children: [
                      const TextSpan(text: 'You have '),
                      TextSpan(
                        text: _formatDuration(pendingFlashPages.fold(0, (sum, w) => sum + w.seconds)),
                        style: const TextStyle(color: Colors.deepPurpleAccent),
                      ),
                      const TextSpan(text: ' of offline recordings to sync.'),
                    ],
                  ),
                ),
              ] else ...[
                Text(
                  'Your pendant is fully synced with the cloud.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 16,
                    height: 1.4,
                  ),
                ),
              ],

              const SizedBox(height: 8),

              // Explanation text
              if ((isSyncing || hasPendingData) && isLimitless) ...[
                Text(
                  'This happens when your pendant is away from your phone for an extended period, the app is closed, or if Bluetooth is turned off on your phone.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.grey.shade600,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
              ],

              const SizedBox(height: 28),

              // Status card
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFF252530),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    // Device image
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      padding: const EdgeInsets.all(6),
                      child: isLimitless
                          ? Assets.images.limitless.image(
                              fit: BoxFit.contain,
                            )
                          : const Icon(
                              Icons.memory_rounded,
                              color: Colors.white70,
                              size: 24,
                            ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            isSyncing
                                ? 'Syncing in progress'
                                : (hasPendingData ? 'Ready to sync' : 'Pendant is up to date'),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            isSyncing
                                ? _getSyncStatusText(progress)
                                : (hasPendingData
                                    ? '${_formatDuration(pendingFlashPages.fold(0, (sum, w) => sum + w.seconds))} waiting'
                                    : 'All audio has been sent to phone'),
                            style: TextStyle(
                              color: Colors.grey.shade500,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Status indicator or button
                    if (isSyncing) ...[
                      const SizedBox(
                        width: 28,
                        height: 28,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: Colors.deepPurpleAccent,
                        ),
                      ),
                    ] else if (hasPendingData) ...[
                      ElevatedButton(
                        onPressed: () => syncProvider.syncWals(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.deepPurple,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20),
                          ),
                          elevation: 0,
                        ),
                        child: const Text(
                          'Sync',
                          style: TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                    ] else ...[
                      Container(
                        width: 44,
                        height: 44,
                        decoration: const BoxDecoration(
                          color: Colors.green,
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          Icons.check_rounded,
                          color: Colors.white,
                          size: 24,
                        ),
                      ),
                    ],
                  ],
                ),
              ),

              // Orphaned files card - files saved to phone but not yet uploaded
              if ((hasOrphanedFiles || isUploadingOrphans) && !isSyncing) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.blue.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.blue.withOpacity(0.3)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.phone_android_rounded, color: Colors.blue.shade400, size: 22),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              isUploadingOrphans
                                  ? 'Uploading to cloud...'
                                  : '$orphanedCount file${orphanedCount > 1 ? 's' : ''} saved on phone',
                              style: TextStyle(color: Colors.blue.shade300, fontSize: 14, fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              isUploadingOrphans ? 'Processing saved recordings' : 'Ready to upload to cloud',
                              style: TextStyle(color: Colors.blue.shade400.withOpacity(0.7), fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      if (isUploadingOrphans)
                        const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.blue,
                          ),
                        )
                      else
                        ElevatedButton(
                          onPressed: () {
                            flashPageSync.uploadOrphanedFiles();
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.blue.shade700,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16),
                            ),
                            elevation: 0,
                          ),
                          child: const Text('Upload', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                        ),
                    ],
                  ),
                ),
              ],

              // Not connected warning
              if (!isConnected && isLimitless) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.orange.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.orange.withOpacity(0.3)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.bluetooth_disabled_rounded, color: Colors.orange.shade400, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Pendant not connected. Connect to sync.',
                          style: TextStyle(color: Colors.orange.shade400, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  String _formatDuration(int seconds) {
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${(seconds / 60).round()} min';
    final hours = seconds ~/ 3600;
    final mins = (seconds % 3600) ~/ 60;
    return '${hours}h ${mins}m';
  }

  String _getSyncStatusText(double progress) {
    if (progress <= 0.4) {
      return 'Syncing from device...';
    } else {
      return 'Processing audio...';
    }
  }
}
