import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/waveform_section.dart';
import 'package:provider/provider.dart';

class WalItemDetailPage extends StatefulWidget {
  final Wal wal;

  const WalItemDetailPage({super.key, required this.wal});

  @override
  State<WalItemDetailPage> createState() => _WalItemDetailPageState();
}

class _WalItemDetailPageState extends State<WalItemDetailPage> {
  List<double>? _waveformData;
  bool _isProcessingWaveform = false;
  SyncProvider? _syncProvider;

  @override
  void initState() {
    super.initState();
    _generateWaveform();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Save reference to SyncProvider to use safely in dispose()
    _syncProvider = context.read<SyncProvider>();
  }

  @override
  void dispose() {
    // Stop audio playback when exiting the detail page
    if (_syncProvider != null && _syncProvider!.isWalPlaying(widget.wal.id)) {
      _syncProvider!.toggleWalPlayback(widget.wal);
    }
    super.dispose();
  }

  Future<void> _generateWaveform() async {
    if (!mounted) return;

    setState(() {
      _isProcessingWaveform = true;
    });

    final syncProvider = context.read<SyncProvider>();
    final waveformData = await syncProvider.getWaveformForWal(widget.wal.id);

    if (mounted) {
      setState(() {
        _waveformData = waveformData;
        _isProcessingWaveform = false;
      });
    }
  }

  PlaybackState _getPlaybackState(SyncProvider syncProvider) {
    return PlaybackState(
      isPlaying: syncProvider.isWalPlaying(widget.wal.id),
      isProcessing: syncProvider.isProcessingAudio && syncProvider.currentPlayingWalId == widget.wal.id,
      isSharing: syncProvider.isWalSharing(widget.wal.id),
      canPlayOrShare: syncProvider.canPlayOrShareWal(widget.wal),
      isSynced: widget.wal.status == WalStatus.synced,
      hasError: syncProvider.failedWal?.id == widget.wal.id,
      currentPosition: syncProvider.currentPosition,
      totalDuration: syncProvider.totalDuration,
      playbackProgress: syncProvider.playbackProgress,
    );
  }

  void _showSnackBar(String message, [Color? backgroundColor]) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: backgroundColor,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        elevation: 0,
        automaticallyImplyLeading: true,
        title: Text('Recording Details', style: Theme.of(context).textTheme.titleLarge),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.more_horiz, color: Colors.white),
            onPressed: () => _showOptionsMenu(context),
          ),
        ],
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Consumer<SyncProvider>(
        builder: (context, syncProvider, child) {
          final playbackState = _getPlaybackState(syncProvider);

          return Column(
            children: [
              // Title section
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                child: Column(
                  children: [
                    Text(
                      dateTimeFormat('dd MMM yyyy', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(
                            fontSize: 28,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      dateTimeFormat('H:mm', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                            color: Colors.grey.shade400,
                            fontSize: 16,
                            fontWeight: FontWeight.w400,
                          ),
                    ),
                    const SizedBox(height: 8),
                    // Privacy notice
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.grey.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.security, color: Colors.grey.shade400, size: 14),
                          const SizedBox(width: 6),
                          Text(
                            'Private & secure on your device',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              // Waveform section - dominant space
              Expanded(
                flex: 6,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: WaveformSection(
                    seconds: widget.wal.seconds,
                    waveformData: _waveformData,
                    isProcessingWaveform: _isProcessingWaveform,
                    playbackState: playbackState,
                  ),
                ),
              ),

              // Timer display
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Consumer<SyncProvider>(
                  builder: (context, syncProvider, child) {
                    final currentPos = playbackState.isPlaying ? playbackState.currentPosition : Duration.zero;
                    return Text(
                      _formatDuration(currentPos),
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(
                            fontSize: 48,
                            fontWeight: FontWeight.w300,
                            letterSpacing: 2,
                          ),
                    );
                  },
                ),
              ),

              // Controls section
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _buildControlButton(
                      icon: Icons.replay_10,
                      onPressed: playbackState.canPlayOrShare && playbackState.isPlaying
                          ? () => _handleSkipBackward(context.read<SyncProvider>())
                          : null,
                      size: 60,
                    ),
                    _buildControlButton(
                      icon: playbackState.isProcessing
                          ? Icons.hourglass_empty
                          : (playbackState.isPlaying ? Icons.pause : Icons.play_arrow),
                      size: 80,
                      backgroundColor: Theme.of(context).colorScheme.secondary,
                      iconColor: Colors.white,
                      onPressed: playbackState.canPlayOrShare && !playbackState.isProcessing
                          ? () => _handlePlayPause(context.read<SyncProvider>())
                          : null,
                    ),
                    _buildControlButton(
                      icon: Icons.forward_10,
                      onPressed: playbackState.canPlayOrShare && playbackState.isPlaying
                          ? () => _handleSkipForward(context.read<SyncProvider>())
                          : null,
                      size: 60,
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 32),
            ],
          );
        },
      ),
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    final milliseconds = (duration.inMilliseconds.remainder(1000) / 10).floor();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')},${milliseconds.toString().padLeft(2, '0')}';
  }

  Widget _buildControlButton({
    required IconData icon,
    VoidCallback? onPressed,
    double size = 48,
    Color? backgroundColor,
    Color? iconColor,
  }) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor ?? Theme.of(context).colorScheme.surface,
        shape: BoxShape.circle,
      ),
      child: IconButton(
        onPressed: onPressed,
        icon: Icon(
          icon,
          color: iconColor ?? Colors.white,
          size: size * 0.4,
        ),
      ),
    );
  }

  Future<void> _handlePlayPause(SyncProvider syncProvider) async {
    if (widget.wal.storage == WalStorage.sdcard) {
      _showSnackBar('Playback for SD card audio is not yet available.', Colors.orange);
      return;
    }

    await syncProvider.toggleWalPlayback(widget.wal);
  }

  Future<void> _handleSkipBackward(SyncProvider syncProvider) async {
    await syncProvider.skipBackward();
  }

  Future<void> _handleSkipForward(SyncProvider syncProvider) async {
    await syncProvider.skipForward();
  }

  void _showOptionsMenu(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.info_outline, color: Colors.white),
              title: Text('Recording Info', style: Theme.of(context).textTheme.bodyMedium),
              onTap: () {
                Navigator.pop(context);
                _showFileDetailsDialog(context);
              },
            ),
            ListTile(
              leading: const Icon(Icons.share, color: Colors.white),
              title: Text('Share Recording', style: Theme.of(context).textTheme.bodyMedium),
              onTap: () {
                Navigator.pop(context);
                _handleShare(context.read<SyncProvider>());
              },
            ),
            ListTile(
              leading: const Icon(Icons.delete, color: Colors.red),
              title:
                  Text('Delete Recording', style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.red)),
              onTap: () {
                Navigator.pop(context); // Close options menu
                _showDeleteDialog(context);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteDialog(BuildContext context) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Delete Recording',
      message: 'Are you sure you want to permanently delete this recording? This can\'t be undone.',
      confirmLabel: 'Delete',
      confirmColor: Colors.red,
    );

    if (confirmed == true && mounted) {
      Navigator.of(context).pop(); // Go back to previous screen
      context.read<SyncProvider>().deleteWal(widget.wal);
    }
  }

  Future<void> _handleShare(SyncProvider syncProvider) async {
    if (widget.wal.storage == WalStorage.sdcard) {
      _showSnackBar('Sharing for SD card audio is not yet available.', Colors.orange);
      return;
    }

    await syncProvider.shareWalAsWav(widget.wal);
  }

  void _showFileDetailsDialog(BuildContext context) {
    final theme = Theme.of(context);
    final recordingDate = DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000);
    final estimatedSize = _estimateFileSize();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 16.0),
                  child: Image.asset(
                    DeviceUtils.getDeviceImagePathByModel(widget.wal.deviceModel),
                    height: 60,
                  ),
                ),
              ),
              _buildDetailRow('Recording ID', widget.wal.id),
              _buildDetailRow('Date & Time', dateTimeFormat('MMM dd, yyyy h:mm:ss a', recordingDate)),
              _buildDetailRow('Duration', secondsToHumanReadable(widget.wal.seconds)),
              _buildDetailRow('Audio Format', widget.wal.codec.toFormattedString()),
              _buildDetailRow('Storage Location', widget.wal.storage == WalStorage.sdcard ? 'SD Card' : 'Phone'),
              _buildDetailRow('Estimated Size', estimatedSize),
              _buildDetailRow('Device Model', widget.wal.deviceModel ?? 'Unknown'),
              if (widget.wal.device.isNotEmpty && widget.wal.device != "phone")
                _buildDetailRow('Device ID', widget.wal.device),
              _buildDetailRow('Status', widget.wal.status == WalStatus.synced ? 'Processed' : 'Unprocessed'),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('Close', style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.secondary)),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium!.copyWith(color: Colors.grey.shade400),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }

  String _estimateFileSize() {
    // Estimate size based on codec, sample rate, channels, and duration
    int bytesPerSecond;
    switch (widget.wal.codec) {
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        bytesPerSecond = widget.wal.codec == BleAudioCodec.opusFS320 ? 40000 : 8000; // ~320kbps vs ~64kbps
        break;
      case BleAudioCodec.pcm16:
        bytesPerSecond = widget.wal.sampleRate * 2 * widget.wal.channel; // 16-bit samples
        break;
      case BleAudioCodec.pcm8:
        bytesPerSecond = widget.wal.sampleRate * 1 * widget.wal.channel; // 8-bit samples
        break;
      case BleAudioCodec.mulaw16:
      case BleAudioCodec.mulaw8:
        bytesPerSecond = widget.wal.sampleRate * 1 * widget.wal.channel; // μ-law is 8-bit encoded
        break;
      default:
        bytesPerSecond = 8000;
    }

    final totalBytes = bytesPerSecond * widget.wal.seconds;
    return _formatBytes(totalBytes);
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}
