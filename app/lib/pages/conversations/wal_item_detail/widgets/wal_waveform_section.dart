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
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          Expanded(
            child: _buildWaveformVisualization(context),
          ),
          const SizedBox(height: 16),
          _buildTimeIndicators(context),
        ],
      ),
    );
  }

  Widget _buildWaveformVisualization(BuildContext context) {
    if (isProcessingWaveform) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(
              color: Colors.white70,
              strokeWidth: 2,
            ),
            const SizedBox(height: 12),
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

  Widget _buildTimeIndicators(BuildContext context) {
    final totalDur = Duration(seconds: wal.seconds);

    // Always show 4 time markers like in ss1.jpeg (0:00, 0:01, 0:02, 0:03)
    List<String> timeMarkers = [];
    final intervalSeconds = (totalDur.inSeconds / 3).ceil(); // Divide into 3 intervals for 4 markers

    for (int i = 0; i <= 3; i++) {
      final seconds = i * intervalSeconds;
      if (seconds <= totalDur.inSeconds) {
        timeMarkers.add(_formatTimeMarker(Duration(seconds: seconds)));
      }
    }

    // Ensure we always have exactly 4 markers
    while (timeMarkers.length < 4) {
      timeMarkers.add(_formatTimeMarker(totalDur));
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: timeMarkers
            .map((marker) => Text(
                  marker,
                  style: Theme.of(context).textTheme.labelMedium!.copyWith(
                        color: Colors.grey.shade500,
                        fontWeight: FontWeight.w400,
                      ),
                ))
            .toList(),
      ),
    );
  }

  String _formatTimeMarker(Duration duration) {
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    return '${minutes}:${seconds.toString().padLeft(2, '0')}';
  }
}
