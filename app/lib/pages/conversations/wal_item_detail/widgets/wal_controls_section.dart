import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';

import '../models/playback_state.dart';

class WalControlsSection extends StatelessWidget {
  final Wal wal;
  final PlaybackState playbackState;
  final Function(String, [Color?]) onShowSnackBar;

  const WalControlsSection({
    super.key,
    required this.wal,
    required this.playbackState,
    required this.onShowSnackBar,
  });

  Future<void> _handlePlayPause(SyncProvider syncProvider) async {
    if (wal.storage == WalStorage.sdcard) {
      onShowSnackBar('Playback for SD card audio is not yet available.', Colors.orange);
      return;
    }

    try {
      await syncProvider.toggleWalPlayback(wal);
    } catch (e) {
      onShowSnackBar('Error playing audio: $e');
    }
  }

  Future<void> _handleSkipBackward(SyncProvider syncProvider) async {
    try {
      await syncProvider.skipBackward();
    } catch (e) {
      onShowSnackBar('Error skipping backward: $e');
    }
  }

  Future<void> _handleSkipForward(SyncProvider syncProvider) async {
    try {
      await syncProvider.skipForward();
    } catch (e) {
      onShowSnackBar('Error skipping forward: $e');
    }
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
        color: backgroundColor ?? Colors.grey.withOpacity(0.2),
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

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _buildControlButton(
            icon: Icons.replay_10,
            onPressed: playbackState.canPlayOrShare && playbackState.isPlaying
                ? () => _handleSkipBackward(context.read<SyncProvider>())
                : null,
            size: 56,
          ),
          _buildControlButton(
            icon: playbackState.isProcessing
                ? Icons.hourglass_empty
                : (playbackState.isPlaying ? Icons.pause : Icons.play_arrow),
            size: 80,
            backgroundColor: Colors.white,
            iconColor: Colors.black,
            onPressed: playbackState.canPlayOrShare && !playbackState.isProcessing
                ? () => _handlePlayPause(context.read<SyncProvider>())
                : null,
          ),
          _buildControlButton(
            icon: Icons.forward_10,
            onPressed: playbackState.canPlayOrShare && playbackState.isPlaying
                ? () => _handleSkipForward(context.read<SyncProvider>())
                : null,
            size: 56,
          ),
        ],
      ),
    );
  }
}
