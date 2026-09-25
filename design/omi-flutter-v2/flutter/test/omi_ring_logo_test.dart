import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../omi_ring_logo.dart';

Widget _host(Widget child, {bool reduceMotion = false}) => MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: Directionality(textDirection: TextDirection.ltr, child: Center(child: child)),
    );

void main() {
  testWidgets('draws at the requested size in every mode', (tester) async {
    for (final mode in OmiRingMode.values) {
      await tester.pumpWidget(_host(OmiRingLogo(size: 48, color: Colors.white, mode: mode)));
      await tester.pump(const Duration(milliseconds: 400));
      final paint = find.descendant(of: find.byType(OmiRingLogo), matching: find.byType(CustomPaint));
      expect(tester.getSize(paint.first), const Size(48, 48));
    }
  });

  testWidgets('animated modes keep ticking; still mode does not schedule frames', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.chase)));
    expect(tester.hasRunningAnimations, isTrue);
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.still)));
    await tester.pump();
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('reduce motion stops the animation', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.orbit), reduceMotion: true));
    await tester.pump();
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('is decorative unless given a label', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(_host(const OmiRingLogo(semanticLabel: 'Omi')));
    expect(find.bySemanticsLabel('Omi'), findsOneWidget);
    handle.dispose();
  });
}
