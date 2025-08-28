import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/time_utils.dart';

import '../models/playback_state.dart';
import 'waveform_painter.dart';

class WalWaveformSection extends StatelessWidget {
  final Wal wal;
  final List<double>? waveformData;
  final bool isProcessingWaveform;
  final PlaybackState playbackState;

  const WalWaveformSection({
    super.key,
    required this.wal,
    required this.waveformData,
    required this.isProcessingWaveform,
    required this.playbackState,
  });

  String _formatDuration(Duration duration) {
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);

    if (hours > 0) {
      return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
    } else {
      return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
    }
  }

  void _handleWaveformTap(
    TapDownDetails details,
    BoxConstraints constraints,
    SyncProvider syncProvider,
  ) {
    if (playbackState.canPlayOrShare && syncProvider.totalDuration.inMilliseconds > 0 && playbackState.isPlaying) {
      final localPosition = details.localPosition;
      final containerWidth = constraints.maxWidth;
      final progress = (localPosition.dx / containerWidth).clamp(0.0, 1.0);
      final seekPosition = Duration(
        milliseconds: (progress * syncProvider.totalDuration.inMilliseconds).round(),
      );
      syncProvider.seekToPosition(seekPosition);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Expanded(
      flex: 2,
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            Expanded(
              child: _buildWaveformVisualization(context),
            ),
            const SizedBox(height: 16),
            _buildTimeIndicators(),
          ],
        ),
      ),
    );
  }

  Widget _buildWaveformVisualization(BuildContext context) {
    if (isProcessingWaveform) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(
              color: Colors.white70,
              strokeWidth: 2,
            ),
            SizedBox(height: 12),
            Text(
              'Analyzing audio...',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 12,
              ),
            ),
          ],
        ),
      );
    }

    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        return LayoutBuilder(
          builder: (context, constraints) {
            return GestureDetector(
              onTapDown: (details) => _handleWaveformTap(details, constraints, syncProvider),
              child: Container(
                width: double.infinity,
                height: double.infinity,
                child: CustomPaint(
                  painter: WaveformPainter(
                    isPlaying: playbackState.isPlaying,
                    waveformData: waveformData,
                    playbackProgress: playbackState.playbackProgress,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildTimeIndicators() {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final currentPos = playbackState.isPlaying ? playbackState.currentPosition : Duration.zero;
        final totalDur = playbackState.isPlaying && playbackState.totalDuration.inMilliseconds > 0
            ? playbackState.totalDuration
            : Duration(seconds: wal.seconds);

        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              _formatDuration(currentPos),
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            ),
            Text(
              _formatDuration(totalDur),
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
            ),
          ],
        );
      },
    );
  }
}
