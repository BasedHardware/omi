import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import '../models/playback_state.dart';

class WalInfoSection extends StatelessWidget {
  final Wal wal;
  final PlaybackState playbackState;
  final Function(String, [Color?]) onShowSnackBar;

  const WalInfoSection({super.key, required this.wal, required this.playbackState, required this.onShowSnackBar});

  Future<void> _handleShare(SyncProvider syncProvider) async {
    if (wal.storage == WalStorage.sdcard) {
      onShowSnackBar('Sharing for SD card audio is not yet available.', Colors.orange);
      return;
    }

    try {
      await syncProvider.shareWalAsWav(wal);
    } catch (e) {
      onShowSnackBar('Error sharing audio: $e');
    }
  }

  void _handleProcessAction(BuildContext context, SyncProvider syncProvider) {
    if (playbackState.hasError) {
      syncProvider.retrySync();
    } else if (playbackState.isSynced) {
      _showResyncDialog(context, syncProvider);
    } else {
      syncProvider.syncWal(wal);
    }
  }

  void _showResyncDialog(BuildContext context, SyncProvider syncProvider) {
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

  @override
  Widget build(BuildContext context) {
    return Expanded(
      flex: 1,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(16)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildAudioInfo(),
            const Spacer(),
            Consumer<SyncProvider>(
              builder: (context, syncProvider, child) {
                return Column(
                  children: [
                    if (playbackState.hasError && syncProvider.syncError != null) _buildErrorSection(syncProvider),
                    _buildActionButtons(context, syncProvider),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAudioInfo() {
    final estimatedSize = _estimateFileSize();
    final recordingDate = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Main title with date
        Text(
          dateTimeFormat('MMM dd, yyyy h:mm a', recordingDate),
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 12),

        // Duration and codec row
        Row(
          children: [
            Expanded(
              child: Row(
                children: [
                  Icon(Icons.access_time, color: Colors.grey.shade400, size: 14),
                  const SizedBox(width: 4),
                  Text(secondsToHumanReadable(wal.seconds),
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
                  const SizedBox(width: 12),
                ],
              ),
            ),
            Icon(Icons.audiotrack, color: Colors.grey.shade400, size: 14),
            const SizedBox(width: 4),
            Text(wal.codec.toFormattedString(), style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
          ],
        ),
        const SizedBox(height: 8),

        // Storage location row
        Row(
          children: [
            Expanded(
              child: Row(
                children: [
                  Icon(
                    wal.storage == WalStorage.sdcard ? Icons.sd_card : Icons.phone_android,
                    color: wal.storage == WalStorage.sdcard ? Colors.purple.shade300 : Colors.blue.shade300,
                    size: 14,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    wal.storage == WalStorage.sdcard ? 'SD Card Storage' : 'Phone Storage',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Row(
              children: [
                Icon(Icons.storage, color: Colors.grey.shade400, size: 14),
                const SizedBox(width: 4),
                Text(estimatedSize, style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
              ],
            )
          ],
        ),
        const SizedBox(height: 8),

        // Device info row
        Row(
          children: [
            Icon(Icons.device_hub, color: Colors.grey.shade400, size: 14),
            const SizedBox(width: 4),
            Expanded(
              child: Text(
                wal.deviceModel ?? "Omi",
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (wal.device != "phone" && wal.device.isNotEmpty) ...[
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(Icons.fingerprint, color: Colors.grey.shade400, size: 14),
                  const SizedBox(width: 4),
                  Text(
                    'Device ID: ${wal.device}',
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ],
          ],
        ),
        const SizedBox(height: 8),

        // Status badges
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: [
            if (playbackState.isSynced)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle, color: Colors.green, size: 12),
                    const SizedBox(width: 4),
                    const Text(
                      'Processed',
                      style: TextStyle(color: Colors.green, fontSize: 11, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }

  String _estimateFileSize() {
    // Estimate size based on codec, sample rate, channels, and duration
    int bytesPerSecond;
    switch (wal.codec) {
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        bytesPerSecond = wal.codec == BleAudioCodec.opusFS320 ? 40000 : 8000; // ~320kbps vs ~64kbps
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = wal.sampleRate * 2 * wal.channel; // 16-bit samples
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = wal.sampleRate * 1 * wal.channel; // 8-bit samples
        break;
      case BleAudioCodec.mulaw16:
      case BleAudioCodec.mulaw8:
        bytesPerSecond = wal.sampleRate * 1 * wal.channel; // μ-law is 8-bit encoded
        break;
      default:
        bytesPerSecond = 8000;
    }

    final totalBytes = bytesPerSecond * wal.seconds;
    return _formatBytes(totalBytes);
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  Widget _buildErrorSection(SyncProvider syncProvider) {
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: Colors.red.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Processing Error',
            style: TextStyle(color: Colors.red, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(syncProvider.syncError!, style: TextStyle(color: Colors.red.shade300, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _buildActionButtons(BuildContext context, SyncProvider syncProvider) {
    return Row(
      children: [
        if (playbackState.canPlayOrShare)
          Expanded(
            child: ElevatedButton.icon(
              onPressed: playbackState.isSharing ? null : () => _handleShare(syncProvider),
              icon: playbackState.isSharing
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.share, size: 18),
              label: Text(playbackState.isSharing ? 'Sharing...' : 'Share'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.grey.shade700,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
        if (playbackState.canPlayOrShare) const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: () => _handleProcessAction(context, syncProvider),
            icon: Icon(
              playbackState.hasError ? Icons.refresh : (playbackState.isSynced ? Icons.refresh : Icons.cloud_upload),
              size: 18,
            ),
            label: Text(playbackState.hasError ? 'Retry' : (playbackState.isSynced ? 'Re-process' : 'Process')),
            style: ElevatedButton.styleFrom(
              backgroundColor: playbackState.hasError
                  ? Colors.red.shade700
                  : (playbackState.isSynced ? Colors.orange : Colors.deepPurple),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
      ],
    );
  }
}
