import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
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

        final isSyncingFromPendant = syncProvider.isSyncingFromPendant;
        final isUploadingToCloud = syncProvider.isUploadingToCloud;

        // Consider sync in progress if EITHER pendant sync OR cloud upload is happening
        final isAnySyncInProgress = isSyncing || isSyncingFromPendant || isUploadingToCloud;
        final hasOrphanedFiles = syncProvider.hasOrphanedFiles;
        final orphanedCount = syncProvider.orphanedFilesCount;

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
                  isAnySyncInProgress
                      ? Icons.sync_rounded
                      : (hasPendingData ? Icons.graphic_eq_rounded : Icons.check_rounded),
                  color: Colors.white,
                  size: 36,
                ),
              ),
              const SizedBox(height: 24),

              // Title
              Text(
                isAnySyncInProgress ? 'Syncing recordings' : (hasPendingData ? 'Recordings to sync' : 'All caught up'),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),

              // Description
              if (isAnySyncInProgress) ...[
                Text(
                  'We\'ll keep syncing your recordings in the background.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 16,
                    height: 1.4,
                  ),
                ),
              ] else if (hasPendingData) ...[
                Text(
                  'You have recordings that aren\'t synced yet.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 16,
                    height: 1.4,
                  ),
                ),
              ] else ...[
                Text(
                  'Everything is already synced.',
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
              if ((isAnySyncInProgress || hasPendingData) && isLimitless) ...[
                Text(
                  isAnySyncInProgress
                      ? 'We\'re catching up on earlier recordings. New moments are still being saved and will appear once sync finishes.'
                      : 'This usually happens when your pendant and phone were apart or Bluetooth was off.',
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
                            isAnySyncInProgress
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
                            isAnySyncInProgress
                                ? _getSyncStatusText(
                                    progress, isSyncingFromPendant, isUploadingToCloud, hasOrphanedFiles, orphanedCount)
                                : (hasPendingData ? 'Tap Sync to start' : 'All recordings are synced'),
                            style: TextStyle(
                              color: Colors.grey.shade500,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Status indicator or button
                    if (isAnySyncInProgress) ...[
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

  String _getSyncStatusText(
      double progress, bool isSyncingFromPendant, bool isUploadingToCloud, bool hasOrphanedFiles, int orphanedCount) {
    if (isSyncingFromPendant) {
      return 'Downloading your recordings…';
    } else if (isUploadingToCloud) {
      if (hasOrphanedFiles && orphanedCount > 0) {
        return 'Uploading to cloud… ($orphanedCount file${orphanedCount > 1 ? 's' : ''} remaining)';
      }
      return 'Uploading to cloud…';
    } else if (progress <= 0.4) {
      return 'Downloading your recordings…';
    } else {
      return 'Processing your audio…';
    }
  }
}
