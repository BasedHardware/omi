import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/components/omi_live_indicators.dart';

/// The live dot pulses at frame rate on three surfaces at once (Home's live episode row, the
/// live episode page header, the device page's live sections). The pulse must stay inside its
/// own repaint boundary, like the activity ring (see `sync_indicator_isolation_test.dart`): an
/// unbounded opacity animation repaints the nearest ancestor display list every frame, which on
/// the episode page header is the whole header layer.
class _PaintCounter extends CustomPainter {
  int paints = 0;

  @override
  void paint(Canvas canvas, Size size) => paints++;

  @override
  bool shouldRepaint(_PaintCounter oldDelegate) => false;
}

void main() {
  testWidgets('live dot pulses without repainting its surroundings', (tester) async {
    final surroundings = _PaintCounter();
    await tester.pumpWidget(MaterialApp(
      home: Center(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CustomPaint(painter: surroundings, size: const Size.square(40)),
            const SizedBox(width: 12),
            const OmiLiveDot(live: true, size: 10),
          ],
        ),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 100));
    final dotFade = find.descendant(of: find.byType(OmiLiveDot), matching: find.byType(FadeTransition));
    final before = tester.widget<FadeTransition>(dotFade).opacity.value;

    surroundings.paints = 0;
    for (var frame = 0; frame < 60; frame++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final after = tester.widget<FadeTransition>(dotFade).opacity.value;

    expect(after, isNot(before), reason: 'the dot must still animate across the window');
    expect(surroundings.paints, 0, reason: 'The pulsing dot must repaint only itself, not the display list around it.');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('live dot is still and quiet when not live', (tester) async {
    final surroundings = _PaintCounter();
    await tester.pumpWidget(MaterialApp(
      home: Center(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CustomPaint(painter: surroundings, size: const Size.square(40)),
            const SizedBox(width: 12),
            const OmiLiveDot(live: false, size: 10),
          ],
        ),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 100));
    expect(
      find.descendant(of: find.byType(OmiLiveDot), matching: find.byType(FadeTransition)),
      findsNothing,
      reason: 'a still dot has no animation',
    );
    surroundings.paints = 0;
    for (var frame = 0; frame < 60; frame++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(surroundings.paints, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
