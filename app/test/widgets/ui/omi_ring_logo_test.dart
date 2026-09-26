import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/ui.dart';

Widget _host(Widget child, {bool reduceMotion = false}) => MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: Directionality(textDirection: TextDirection.ltr, child: Center(child: child)),
    );

void main() {
  testWidgets('draws at the requested size in every mode', (tester) async {
    for (final mode in OmiRingMode.values) {
      await tester.pumpWidget(_host(OmiRingLogo(size: 48, color: OmiColors.textPrimary, mode: mode)));
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

  testWidgets('switching from still to an animated mode starts the animation', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.still)));
    expect(tester.hasRunningAnimations, isFalse);
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.breathe)));
    expect(tester.hasRunningAnimations, isTrue);
  });

  testWidgets('a finite number of loops comes to rest, so an idle control stops drawing', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.breathe, loops: 3)));
    expect(tester.hasRunningAnimations, isTrue);
    await tester.pumpAndSettle();
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('reduce motion stops the animation', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.orbit), reduceMotion: true));
    await tester.pump();
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('turning on reduce motion while animating stops it, and turning it off resumes', (tester) async {
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.chase)));
    expect(tester.hasRunningAnimations, isTrue);
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.chase), reduceMotion: true));
    expect(tester.hasRunningAnimations, isFalse);
    await tester.pumpWidget(_host(const OmiRingLogo(mode: OmiRingMode.chase)));
    expect(tester.hasRunningAnimations, isTrue);
  });

  testWidgets('is decorative unless given a label', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(_host(const OmiRingLogo()));
    expect(find.bySemanticsLabel('Omi'), findsNothing);
    await tester.pumpWidget(_host(const OmiRingLogo(semanticLabel: 'Omi')));
    expect(find.bySemanticsLabel('Omi'), findsOneWidget);
    handle.dispose();
  });
}
