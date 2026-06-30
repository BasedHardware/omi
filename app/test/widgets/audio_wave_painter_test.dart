import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';

void main() {
  group('AudioWavePainter', () {
    test('shouldRepaint returns false for identical levels', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);

      expect(painter1.shouldRepaint(painter2), false);
    });

    test('shouldRepaint returns true when levels length differs', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);

      expect(painter1.shouldRepaint(painter2), true);
    });

    test('shouldRepaint returns true when level differs by more than 0.005', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.65, 0.7]);

      expect(painter1.shouldRepaint(painter2), true);
    });

    test('shouldRepaint returns false when level differs by less than 0.005', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.604, 0.7]); // ~0.004 diff - below threshold

      expect(painter1.shouldRepaint(painter2), false);
    });

    // Boundary tests for the 0.005 threshold (implementation uses > 0.005, not >=).
    // Note: floating point precision means 0.505 - 0.5 = 0.005000000000000004, not exactly 0.005.
    test('shouldRepaint returns true when level differs by clearly more than 0.005', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.62, 0.7]); // 0.02 diff - clearly above threshold

      expect(painter1.shouldRepaint(painter2), true);
    });

    test('shouldRepaint returns false when level differs by clearly less than 0.005', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.602, 0.7]); // 0.002 diff - clearly below threshold

      expect(painter1.shouldRepaint(painter2), false);
    });

    test('shouldRepaint handles negative differences correctly (uses absolute value)', () {
      final painter1 = AudioWavePainter(levels: [0.5, 0.6, 0.7]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.55, 0.7]); // -0.05 diff, abs = 0.05

      expect(painter1.shouldRepaint(painter2), true);
    });

    test('shouldRepaint at the 0.005 boundary is affected by floating point precision', () {
      // Due to floating point: 0.505 - 0.5 = 0.005000000000000004 > 0.005
      // This documents the actual behavior - slight imprecision at the boundary.
      final painter1 = AudioWavePainter(levels: [0.5, 0.5, 0.5]);
      final painter2 = AudioWavePainter(levels: [0.5, 0.505, 0.5]);
      // Because of floating point, this returns true (repaint triggered)
      expect(painter1.shouldRepaint(painter2), true);
    });

    test('shouldRepaint returns false for empty levels', () {
      final painter1 = AudioWavePainter(levels: []);
      final painter2 = AudioWavePainter(levels: []);

      expect(painter1.shouldRepaint(painter2), false);
    });

    test('paint handles empty levels without error', () {
      final painter = AudioWavePainter(levels: []);
      final recorder = PictureRecorder();
      final canvas = Canvas(recorder);

      // Should not throw divide-by-zero or any error
      expect(() => painter.paint(canvas, const Size(100, 40)), returnsNormally);
    });

    test('painter creates defensive copy of levels list', () {
      final originalLevels = [0.5, 0.6, 0.7];
      final painter = AudioWavePainter(levels: originalLevels);

      // Modify original list
      originalLevels[0] = 1.0;

      // Painter should still have original values
      expect(painter.levels[0], 0.5);
    });
  });
}
