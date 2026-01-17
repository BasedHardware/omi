import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';

class LimitlessSyncCardWidget extends StatelessWidget {
  const LimitlessSyncCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer2<DeviceProvider, SyncProvider>(
      builder: (context, deviceProvider, syncProvider, child) {
        // Only show for connected Limitless device
        final device = deviceProvider.pairedDevice;
        if (device == null || !deviceProvider.isConnected || device.type != DeviceType.limitless) {
          return const SizedBox();
        }

        // Check if there are pending flash pages
        final pendingFlashPages =
            syncProvider.allWals.where((w) => w.storage == WalStorage.flashPage && w.status == WalStatus.miss).toList();

        if (pendingFlashPages.isEmpty && !syncProvider.isSyncing) {
          return const SizedBox();
        }

        final isSyncing = syncProvider.isSyncing;
        final progress = syncProvider.walsSyncedProgress;

        return Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1F1F25),
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
          margin: const EdgeInsets.fromLTRB(16, 15, 16, 0),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.sync,
                    color: Colors.white70,
                    size: 22,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      isSyncing ? 'Syncing your recordings' : 'Sync your recordings',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                      ),
                    ),
                  ),
                  if (!isSyncing)
                    ElevatedButton(
                      onPressed: () => syncProvider.syncWals(),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.deepPurple,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: const Text('Sync Now'),
                    )
                  else
                    Text(
                      '${(progress * 100).toInt()}%',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                ],
              ),
              // Progress bar when syncing
              if (isSyncing) ...[
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: progress > 0 ? progress : null,
                    backgroundColor: Colors.grey.shade800,
                    color: Colors.deepPurple,
                    minHeight: 4,
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}
