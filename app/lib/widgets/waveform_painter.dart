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
    // Always draw the full number of bars to fill the width
    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth + spacing);

      // Map this bar index to the waveform data
      double amplitude = 0.0;
      if (waveformData!.isNotEmpty) {
        // Calculate which data point(s) this bar represents
        final dataIndex = (i * waveformData!.length / barCount).floor();
        if (dataIndex < waveformData!.length) {
          amplitude = waveformData![dataIndex];
        }
      }

      // Use raw amplitude with no adjustments
      final height = amplitude * size.height;
      final centerY = size.height / 2;

      // Draw waveform bar from center, extending both up and down
      final halfHeight = height / 2;

      final progressBarIndex = (barCount * playbackProgress).floor();
      final useActivePaint = isPlaying && i <= progressBarIndex;

      // Use more dynamic scaling with lower minimum height
      final minHeight = 1.0; // Lower minimum for more dynamic range
      final scaledHeight = height * 1.2; // Slightly amplify the height
      final displayHeight = math.max(scaledHeight, minHeight);
      final displayHalfHeight = displayHeight / 2;

      canvas.drawLine(
        Offset(x, centerY - displayHalfHeight),
        Offset(x, centerY + displayHalfHeight),
        useActivePaint ? activePaint : paint,
      );
    }

    // Draw progress indicator dot - more prominent like in ss1.jpeg
    if (isPlaying && playbackProgress > 0) {
      final progressX = (barCount * playbackProgress) * (barWidth + spacing);
      final dotPaint = Paint()
        ..color = const Color(0xFF4A90E2) // Blue color like in the image
        ..style = PaintingStyle.fill;

      // Draw the progress dot above the waveform
      canvas.drawCircle(
        Offset(progressX, size.height * 0.05), // Position higher up
        6.0, // Larger dot
        dotPaint,
      );

      // Draw a subtle vertical line from dot to waveform
      final linePaint = Paint()
        ..color = const Color(0xFF4A90E2).withOpacity(0.5)
        ..strokeWidth = 1.0;

      canvas.drawLine(
        Offset(progressX, size.height * 0.05 + 6),
        Offset(progressX, size.height * 0.95),
        linePaint,
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
    // Paint a single center line when no waveform data is available
    final centerY = size.height / 2;
    canvas.drawLine(
      Offset(0, centerY),
      Offset(size.width, centerY),
      paint..strokeWidth = 1,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) {
    if (oldDelegate is! WaveformPainter) return true;

    // Only repaint if there are significant changes to avoid excessive redraws
    final progressDiff = (oldDelegate.playbackProgress - playbackProgress).abs();

    return oldDelegate.isPlaying != isPlaying ||
        oldDelegate.waveformData != waveformData ||
        progressDiff > 0.01; // Only repaint if progress changed by more than 1%
  }
}
