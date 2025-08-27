import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/widgets/appbar_with_banner.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'synced_conversations_page.dart';

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
    if (startedAt == null) {
      return 0.0;
    }
    if (eta == 0) {
      return 0.01;
    }
    final elapsed = DateTime.now().difference(startedAt).inSeconds;
    final progress = elapsed / eta;
    return progress.clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final isPlaying = syncProvider.isWalPlaying(wal.id);
        final isProcessing = syncProvider.isProcessingAudio && syncProvider.currentPlayingWalId == wal.id;
        final isSharingThisWal = syncProvider.isWalSharing(wal.id);
        final isAnyWalSharing = syncProvider.isSharingAudio;
        final canPlayOrShare = syncProvider.canPlayOrShareWal(wal);
        final isSynced = wal.status == WalStatus.synced;
        final hasError = syncProvider.failedWal?.id == wal.id;

        return GestureDetector(
          onTap: () async {
            // TODO
          },
          child: Padding(
            padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
            child: Container(
              width: double.maxFinite,
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(16.0),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16.0),
                child: Dismissible(
                  key: Key(wal.id),
                  direction: wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
                  confirmDismiss: (direction) async {
                    return await showDialog(
                      context: context,
                      builder: (BuildContext context) {
                        return AlertDialog(
                          backgroundColor: const Color(0xFF1F1F25),
                          title: const Text("Confirm Deletion", style: TextStyle(color: Colors.white)),
                          content: const Text(
                              "Are you sure you want to delete this audio file? This action cannot be undone.",
                              style: TextStyle(color: Colors.white70)),
                          actions: <Widget>[
                            TextButton(
                              onPressed: () => Navigator.of(context).pop(false),
                              child: const Text("Cancel", style: TextStyle(color: Colors.grey)),
                            ),
                            TextButton(
                              onPressed: () => Navigator.of(context).pop(true),
                              child: const Text("Delete", style: TextStyle(color: Colors.red)),
                            ),
                          ],
                        );
                      },
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
                    padding: const EdgeInsetsDirectional.all(0),
                    child: Column(
                      mainAxisSize: MainAxisSize.max,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Row(
                            children: [
                              // Device icon and info
                              Container(
                                width: 40,
                                height: 40,
                                decoration: BoxDecoration(
                                  color: wal.storage == WalStorage.sdcard
                                      ? Colors.purple.withOpacity(0.2)
                                      : Colors.blue.withOpacity(0.2),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Icon(
                                  wal.storage == WalStorage.sdcard ? Icons.sd_card : Icons.phone_android,
                                  color:
                                      wal.storage == WalStorage.sdcard ? Colors.purple.shade300 : Colors.blue.shade300,
                                  size: 20,
                                ),
                              ),
                              const SizedBox(width: 12),
                              // Main content
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          secondsToHumanReadable(wal.seconds),
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.grey.withOpacity(0.2),
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: Text(
                                              wal.codec.toFormattedString(),
                                              style: TextStyle(
                                                color: Colors.grey.shade300,
                                                fontSize: 10,
                                                fontWeight: FontWeight.w500,
                                              ),
                                              overflow: TextOverflow.fade,
                                              softWrap: false,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 4),
                                    Row(
                                      children: [
                                        Text(
                                          wal.deviceModel ?? "Phone Microphone",
                                          style: TextStyle(
                                            color: Colors.grey.shade400,
                                            fontSize: 12,
                                          ),
                                        ),
                                        if (isSynced) ...[
                                          const SizedBox(width: 8),
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.green.withOpacity(0.2),
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: const Text(
                                              'Processed ✅',
                                              style: TextStyle(
                                                color: Colors.green,
                                                fontSize: 10,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                              // Actions
                              if (isSynced)
                                PopupMenuButton<String>(
                                  onSelected: (value) async {
                                    if (value == 'reprocess') {
                                      WalListItem.showResyncDialog(context, wal, syncProvider);
                                    } else if (value == 'play') {
                                      try {
                                        await syncProvider.toggleWalPlayback(wal);
                                      } catch (e) {
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(content: Text('Error playing audio: $e')),
                                          );
                                        }
                                      }
                                    } else if (value == 'share') {
                                      if (wal.storage == WalStorage.sdcard) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          const SnackBar(
                                            content: Text('Sharing for SD card audio is not yet available.'),
                                            backgroundColor: Colors.orange,
                                          ),
                                        );
                                        return;
                                      }
                                      try {
                                        await syncProvider.shareWalAsWav(wal);
                                      } catch (e) {
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(content: Text('Error sharing audio: $e')),
                                          );
                                        }
                                      }
                                    }
                                  },
                                  itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
                                    const PopupMenuItem<String>(
                                      value: 'reprocess',
                                      child: ListTile(leading: Icon(Icons.refresh), title: Text('Re-process')),
                                    ),
                                    if (canPlayOrShare)
                                      PopupMenuItem<String>(
                                        value: 'play',
                                        child: ListTile(
                                            leading: Icon(isPlaying ? Icons.pause : Icons.play_arrow),
                                            title: Text(isPlaying ? 'Pause Audio' : 'Play Audio')),
                                      ),
                                    if (canPlayOrShare)
                                      const PopupMenuItem<String>(
                                        value: 'share',
                                        child: ListTile(leading: Icon(Icons.share), title: Text('Share Audio')),
                                      ),
                                  ],
                                  icon: const Icon(Icons.more_vert, color: Colors.white70),
                                )
                              else if (hasError)
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (canPlayOrShare)
                                      IconButton(
                                        onPressed: isProcessing
                                            ? null
                                            : () async {
                                                if (wal.storage == WalStorage.sdcard) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(
                                                      content: Text('Playback for SD card audio is not yet available.'),
                                                      backgroundColor: Colors.orange,
                                                    ),
                                                  );
                                                  return;
                                                }
                                                try {
                                                  await syncProvider.toggleWalPlayback(wal);
                                                } catch (e) {
                                                  if (context.mounted) {
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      SnackBar(
                                                        content: Text('Error playing audio: $e'),
                                                        backgroundColor: Colors.red.shade700,
                                                      ),
                                                    );
                                                  }
                                                }
                                              },
                                        icon: isProcessing
                                            ? const SizedBox(
                                                width: 16,
                                                height: 16,
                                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70))
                                            : Icon(
                                                isPlaying ? Icons.pause_circle_filled : Icons.play_circle_filled,
                                                color: isPlaying ? Colors.orange : Colors.white70,
                                                size: 24,
                                              ),
                                        tooltip: isProcessing ? 'Processing...' : (isPlaying ? 'Pause' : 'Play'),
                                      ),
                                    if (canPlayOrShare)
                                      IconButton(
                                        onPressed: isSharingThisWal
                                            ? null
                                            : () async {
                                                if (wal.storage == WalStorage.sdcard) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(
                                                      content: Text('Sharing for SD card audio is not yet available.'),
                                                      backgroundColor: Colors.orange,
                                                    ),
                                                  );
                                                  return;
                                                }
                                                try {
                                                  await syncProvider.shareWalAsWav(wal);
                                                } catch (e) {
                                                  if (context.mounted) {
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      SnackBar(
                                                        content: Text('Error sharing audio: $e'),
                                                        backgroundColor: Colors.red.shade700,
                                                      ),
                                                    );
                                                  }
                                                }
                                              },
                                        icon: isSharingThisWal
                                            ? const SizedBox(
                                                width: 16,
                                                height: 16,
                                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70))
                                            : const Icon(Icons.share_rounded, color: Colors.white70, size: 20),
                                        tooltip: isSharingThisWal ? 'Sharing...' : 'Share as WAV',
                                      ),
                                    ElevatedButton.icon(
                                      onPressed: () => syncProvider.retrySync(),
                                      icon: const Icon(Icons.refresh, size: 14),
                                      label: const Text('Retry'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.red.shade700,
                                        foregroundColor: Colors.white,
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(20),
                                        ),
                                      ),
                                    ),
                                  ],
                                )
                              else if (wal.isSyncing)
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: Colors.orange.withOpacity(0.2),
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const SizedBox(
                                        width: 12,
                                        height: 12,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.orange,
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        "${wal.syncEtaSeconds != null ? "${wal.syncEtaSeconds}s" : "..."} ETA",
                                        style: const TextStyle(
                                            color: Colors.orange, fontSize: 12, fontWeight: FontWeight.w600),
                                      ),
                                    ],
                                  ),
                                )
                              else
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (canPlayOrShare)
                                      IconButton(
                                        onPressed: isProcessing
                                            ? null
                                            : () async {
                                                if (wal.storage == WalStorage.sdcard) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(
                                                      content: Text('Playback for SD card audio is not yet available.'),
                                                      backgroundColor: Colors.orange,
                                                    ),
                                                  );
                                                  return;
                                                }
                                                try {
                                                  await syncProvider.toggleWalPlayback(wal);
                                                } catch (e) {
                                                  if (context.mounted) {
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      SnackBar(
                                                        content: Text('Error playing audio: $e'),
                                                        backgroundColor: Colors.red.shade700,
                                                      ),
                                                    );
                                                  }
                                                }
                                              },
                                        icon: isProcessing
                                            ? const SizedBox(
                                                width: 16,
                                                height: 16,
                                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70))
                                            : Icon(
                                                isPlaying ? Icons.pause_circle_filled : Icons.play_circle_filled,
                                                color: isPlaying ? Colors.orange : Colors.white70,
                                                size: 24,
                                              ),
                                        tooltip: isProcessing ? 'Processing...' : (isPlaying ? 'Pause' : 'Play'),
                                      ),
                                    if (canPlayOrShare)
                                      IconButton(
                                        onPressed: isSharingThisWal
                                            ? null
                                            : () async {
                                                if (wal.storage == WalStorage.sdcard) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(
                                                      content: Text('Sharing for SD card audio is not yet available.'),
                                                      backgroundColor: Colors.orange,
                                                    ),
                                                  );
                                                  return;
                                                }
                                                try {
                                                  await syncProvider.shareWalAsWav(wal);
                                                } catch (e) {
                                                  if (context.mounted) {
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      SnackBar(
                                                        content: Text('Error sharing audio: $e'),
                                                        backgroundColor: Colors.red.shade700,
                                                      ),
                                                    );
                                                  }
                                                }
                                              },
                                        icon: isSharingThisWal
                                            ? const SizedBox(
                                                width: 16,
                                                height: 16,
                                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70))
                                            : const Icon(Icons.share_rounded, color: Colors.white70, size: 20),
                                        tooltip: isSharingThisWal ? 'Sharing...' : 'Share as WAV',
                                      ),
                                    ElevatedButton(
                                      onPressed: () {
                                        syncProvider.syncWal(wal);
                                      },
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.deepPurple,
                                        foregroundColor: Colors.white,
                                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(20),
                                        ),
                                      ),
                                      child: const Text(
                                        'Process',
                                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                                      ),
                                    ),
                                  ],
                                ),
                            ],
                          ),
                        ),
                        if (hasError && syncProvider.syncError != null)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                            child: Text(
                              syncProvider.syncError!,
                              style: TextStyle(color: Colors.red.shade300, fontSize: 12),
                            ),
                          ),
                        if (wal.isSyncing && wal.status != WalStatus.synced)
                          LinearProgressIndicator(
                            value: calculateProgress(wal.syncStartedAt ?? DateTime.now(), wal.syncEtaSeconds ?? 0),
                            backgroundColor: Colors.grey[800],
                            color: Colors.white,
                            minHeight: 4,
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  static void showResyncDialog(BuildContext context, Wal wal, SyncProvider syncProvider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Reprocess Audio File', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This will reprocess the audio file and may create a new conversation or update an existing one.',
              style: TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 12),
            Text(
              'File: ${secondsToHumanReadable(wal.seconds)}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
            Text(
              'Recorded: ${dateTimeFormat('MMM dd, h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000))}',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              syncProvider.resyncWal(wal);
            },
            child: const Text('Reprocess', style: TextStyle(color: Colors.orange)),
          ),
        ],
      ),
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

class SyncWalGroupWidget extends StatelessWidget {
  final List<Wal> wals;
  final DateTime date;
  final bool isFirst;
  const SyncWalGroupWidget({super.key, required this.wals, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    if (wals.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DateTimeListItem(date: date, isFirst: isFirst),
          ...wals.map((wal) {
            return WalListItem(wal: wal, walIdx: wals.indexOf(wal), date: date);
          }),
          const SizedBox(height: 16),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
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

  void _showDeleteProcessedDialog(BuildContext context, SyncProvider provider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text('Delete All Processed Files', style: TextStyle(color: Colors.white)),
        content: const Text(
          'This will permanently delete all processed audio files from your device. This action cannot be undone.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () async {
              Navigator.of(context).pop();
              await provider.deleteAllSyncedWals();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('All processed audio files have been deleted'),
                    backgroundColor: Colors.green,
                  ),
                );
              }
            },
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
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
          border: Border.all(color: Colors.red.withOpacity(0.3)),
        ),
        child: Column(
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error_outline, color: Colors.red, size: 24),
                SizedBox(width: 12),
                Text(
                  'Processing Failed',
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
                  'Retry Processing',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red.shade700,
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
          border: Border.all(color: Colors.orange.withOpacity(0.3)),
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
                  'Processing Audio Files...',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (syncProvider.walsSyncedProgress > 0)
              LinearProgressIndicator(
                value: syncProvider.walsSyncedProgress,
                backgroundColor: Colors.grey[800],
                color: Colors.orange,
                minHeight: 6,
              ),
            const SizedBox(height: 12),
            const Text(
              'Keep the app open while processing.',
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
          border: Border.all(color: Colors.green.withOpacity(0.3)),
        ),
        child: Column(
          children: [
            const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.check_circle, color: Colors.green, size: 24),
                SizedBox(width: 12),
                Text(
                  'Processing Complete!',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              '${syncProvider.syncedConversationsPointers.length} audio files processed successfully.',
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
                  'View Processed Conversations',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green,
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
              Text(
                secondsToHumanReadable(totalSecondsToProcess),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '${stats.missedFiles} audio files ready to process',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
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
                  _buildStatItem('On SD Card', '${stats.sdcardFiles}'),
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
                            syncProvider.syncWals();
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: const Row(
                                  children: [
                                    Icon(Icons.wifi_off, color: Colors.white),
                                    SizedBox(width: 8),
                                    Text('Internet connection required'),
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
                  label: const Text(
                    'Process All Audio Files',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurple,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 2,
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
        var provider = Provider.of<SyncProvider>(context, listen: false);
        provider.clearSyncResult();
      },
      child: Consumer<SyncProvider>(builder: (context, syncProvider, child) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('Local Audio Storage'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            actions: [
              FutureBuilder<WalStats>(
                future: syncProvider.getWalStats(),
                builder: (context, snapshot) {
                  if (snapshot.hasData && snapshot.data!.syncedFiles > 0) {
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
                  }
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
                    _buildSummaryCard(syncProvider),
                    const Padding(
                      padding: EdgeInsets.fromLTRB(24, 0, 24, 12),
                      child: Text(
                        'Audio recordings from your Omi device, including live recordings and files from the device\'s SD card. Phone microphone recordings are not stored here.',
                        style: TextStyle(color: Colors.white70, fontSize: 14),
                        textAlign: TextAlign.center,
                      ),
                    ),
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
                  if (allWals.isEmpty) {
                    return SliverToBoxAdapter(
                      child: Container(
                        margin: const EdgeInsets.all(32.0),
                        padding: const EdgeInsets.all(32.0),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1F25),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.grey.withOpacity(0.2)),
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
                                Icons.folder_open,
                                color: Colors.grey,
                                size: 48,
                              ),
                            ),
                            const SizedBox(height: 16),
                            const Text(
                              'No Audio Files Found',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              'Connect your Omi device and start recording to see audio files here. Phone microphone recordings are processed directly and not stored locally.',
                              style: TextStyle(color: Colors.grey, fontSize: 14),
                              textAlign: TextAlign.center,
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  return WalsListWidget(wals: allWals);
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

class WalsListWidget extends StatelessWidget {
  final List<Wal> wals;
  const WalsListWidget({super.key, required this.wals});

  @override
  Widget build(BuildContext context) {
    var groupedWals = _groupWalsByDate(wals);

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        childCount: groupedWals.keys.length,
        (context, index) {
          var date = groupedWals.keys.toList()[index];
          List<Wal> wals = groupedWals[date] ?? [];
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (index == 0) const SizedBox(height: 16),
              SyncWalGroupWidget(
                isFirst: index == 0,
                wals: wals,
                date: date,
              ),
            ],
          );
        },
      ),
    );
  }
}
