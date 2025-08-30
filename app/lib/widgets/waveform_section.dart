import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/models/playback_state.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/widgets/waveform_painter.dart';
import 'package:provider/provider.dart';

class WaveformSection extends StatefulWidget {
  final int seconds;
  final List<double>? waveformData;
  final bool isProcessingWaveform;
  final PlaybackState playbackState;

  const WaveformSection({
    super.key,
    required this.seconds,
    required this.waveformData,
    required this.isProcessingWaveform,
    required this.playbackState,
  });

  @override
  State<WaveformSection> createState() => _WaveformSectionState();
}

class _WaveformSectionState extends State<WaveformSection> {
  Timer? _progressUpdateTimer;
  double _lastProgress = 0.0;

  @override
  void initState() {
    super.initState();
    _startProgressTimer();
  }

  @override
  void dispose() {
    _progressUpdateTimer?.cancel();
    super.dispose();
  }

  void _startProgressTimer() {
    _progressUpdateTimer = Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (mounted && widget.playbackState.isPlaying) {
        final currentProgress = widget.playbackState.playbackProgress;
        if ((currentProgress - _lastProgress).abs() > 0.01) {
          _lastProgress = currentProgress;
          setState(() {});
        }
      }
    });
  }

  void _handleWaveformTap(
    TapDownDetails details,
    BoxConstraints constraints,
    SyncProvider syncProvider,
  ) {
    if (widget.playbackState.canPlayOrShare &&
        syncProvider.totalDuration.inMilliseconds > 0 &&
        widget.playbackState.isPlaying) {
      final localPosition = details.localPosition;
      final containerWidth = constraints.maxWidth;
      final progress = (localPosition.dx / containerWidth).clamp(0.0, 1.0);
      final seekPosition = Duration(
        milliseconds: (progress * syncProvider.totalDuration.inMilliseconds).round(),
      );

      // Perform seek operation asynchronously to avoid blocking UI
      Future.microtask(() => syncProvider.seekToPosition(seekPosition));
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
    if (widget.isProcessingWaveform) {
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
              'Loading your recording...',
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
                child: RepaintBoundary(
                  child: CustomPaint(
                    painter: WaveformPainter(
                      isPlaying: widget.playbackState.isPlaying,
                      waveformData: widget.waveformData,
                      playbackProgress: _lastProgress,
                    ),
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
    final totalDur = Duration(seconds: widget.seconds);

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
