import 'dart:math';
import 'dart:math' as math;
import 'package:flutter/material.dart';

class WaveformPainter extends CustomPainter {
  final bool isPlaying;
  final List<double>? waveformData;
  final double playbackProgress;

  const WaveformPainter({
    required this.isPlaying,
    this.waveformData,
    this.playbackProgress = 0.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.grey.shade600
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;

    final activePaint = Paint()
      ..color = Colors.white
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;

    final barWidth = 2.0;
    final spacing = 2.0;
    final barCount = (size.width / (barWidth + spacing)).floor();

    if (waveformData != null && waveformData!.isNotEmpty) {
      _paintRealWaveform(canvas, size, paint, activePaint, barWidth, spacing, barCount);
    } else {
      _paintFallbackWaveform(canvas, size, paint, activePaint, barWidth, spacing, barCount);
    }
  }

  void _paintRealWaveform(
    Canvas canvas,
    Size size,
    Paint paint,
    Paint activePaint,
    double barWidth,
    double spacing,
    int barCount,
  ) {
    final dataPointsPerBar = (waveformData!.length / barCount).ceil();

    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth + spacing);

      // Get average amplitude for this bar
      double amplitude = 0.0;
      int count = 0;
      for (int j = i * dataPointsPerBar; j < (i + 1) * dataPointsPerBar && j < waveformData!.length; j++) {
        amplitude += waveformData![j];
        count++;
      }
      if (count > 0) {
        amplitude /= count;
      }

      // Ensure minimum height for visibility
      amplitude = math.max(amplitude, 0.05);

      final height = amplitude * size.height * 0.8;
      final y = (size.height - height) / 2;

      final progressBarIndex = (barCount * playbackProgress).floor();
      final useActivePaint = isPlaying && i <= progressBarIndex;

      canvas.drawLine(
        Offset(x, y),
        Offset(x, y + height),
        useActivePaint ? activePaint : paint,
      );
    }
  }

  void _paintFallbackWaveform(
    Canvas canvas,
    Size size,
    Paint paint,
    Paint activePaint,
    double barWidth,
    double spacing,
    int barCount,
  ) {
    final random = Random(42); // Fixed seed for consistent waveform

    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth + spacing);
      final height = (random.nextDouble() * 0.7 + 0.1) * size.height;
      final y = (size.height - height) / 2;

      final progressBarIndex = (barCount * playbackProgress).floor();
      final useActivePaint = isPlaying && i <= progressBarIndex;

      canvas.drawLine(
        Offset(x, y),
        Offset(x, y + height),
        useActivePaint ? activePaint : paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) {
    return oldDelegate is WaveformPainter &&
        (oldDelegate.isPlaying != isPlaying ||
            oldDelegate.waveformData != waveformData ||
            oldDelegate.playbackProgress != playbackProgress);
  }
}
