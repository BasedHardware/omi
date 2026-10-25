import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/ui/components/omi_live_indicators.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/widgets/scanning_ripple.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

class _Surroundings extends CustomPainter {
  int paints = 0;
  @override
  void paint(Canvas canvas, Size size) => paints++;
  @override
  bool shouldRepaint(_Surroundings oldDelegate) => false;
}

void main() {
  testWidgets('breathing dot preserves the original ring pixels throughout its cycle', (tester) async {
    for (final elapsedMs in [0, 600, 1200, 1800]) {
      final t = Curves.easeOut.transform(elapsedMs / 2400);
      final color = OmiColors.textPrimary;
      await tester.pumpWidget(MaterialApp(
        home: Center(
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            RepaintBoundary(key: const Key('actual'), child: OmiBreathingDot(key: ValueKey(elapsedMs))),
            RepaintBoundary(
              key: const Key('reference'),
              // Static snapshots of the original widget rendering, retained
              // only as a visual oracle for the paint-only implementation.
              child: SizedBox.square(
                dimension: 18,
                child: Stack(alignment: Alignment.center, children: [
                  Opacity(
                    opacity: (1 - t) * 0.6,
                    child: Container(
                      width: 6 * (1 + 1.6 * t),
                      height: 6 * (1 + 1.6 * t),
                      decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: color, width: 1)),
                    ),
                  ),
                  Container(width: 6, height: 6, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                ]),
              ),
            ),
          ]),
        ),
      ));
      await tester.pump();
      await tester.pump(Duration(milliseconds: elapsedMs));
      final pixels = (await tester.runAsync(() async {
        final result = <List<int>>[];
        for (final key in ['actual', 'reference']) {
          final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(Key(key)));
          final image = await boundary.toImage(pixelRatio: 3);
          final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
          result.add(data!.buffer.asUint8List());
          image.dispose();
        }
        return result;
      }))!;
      expect(pixels.first.length, pixels.last.length);
      var maxDelta = 0;
      for (var i = 0; i < pixels.first.length; i++) {
        final delta = (pixels.first[i] - pixels.last[i]).abs();
        if (delta > maxDelta) maxDelta = delta;
      }
      debugPrint('GLOBAL breathingDot visual elapsedMs=$elapsedMs maxRgbaDelta=$maxDelta');
      expect(maxDelta, lessThanOrEqualTo(3), reason: 'only alpha quantization may differ from the original layer');
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });

  for (final semantics in [false, true]) {
    testWidgets('breathing dot only paints on animation frames semantics=$semantics', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        final surroundings = _Surroundings();
        await tester.pumpWidget(MaterialApp(
          home: Center(
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              CustomPaint(painter: surroundings, size: const Size.square(40)),
              const OmiBreathingDot(),
            ]),
          ),
        ));
        await tester.pump(const Duration(milliseconds: 100));
        final builds = <String, int>{};
        final previous = debugOnRebuildDirtyWidget;
        debugOnRebuildDirtyWidget = (element, builtOnce) {
          builds.update(element.widget.runtimeType.toString(), (n) => n + 1, ifAbsent: () => 1);
          previous?.call(element, builtOnce);
        };
        addTearDown(() => debugOnRebuildDirtyWidget = previous);
        surroundings.paints = 0;
        for (var frame = 0; frame < 60; frame++) {
          await tester.pump(const Duration(milliseconds: 16));
        }
        debugOnRebuildDirtyWidget = previous;
        final opacitySites =
            find.descendant(of: find.byType(OmiBreathingDot), matching: find.byType(Opacity)).evaluate().length;
        debugPrint('GLOBAL breathingDot semantics=$semantics frames=60 rebuilds=$builds '
            'opacitySites=$opacitySites surroundingPaints=${surroundings.paints} '
            'transientCallbacks=${tester.binding.transientCallbackCount}');
        expect(builds, isEmpty, reason: 'a decorative live mark must not build/layout widgets at frame rate');
        expect(opacitySites, 0, reason: 'draw the single ring with alpha instead of compositing an opacity subtree');
        expect(surroundings.paints, 0);
        expect(tester.binding.transientCallbackCount, 1, reason: 'the live ring still animates');
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        handle?.dispose();
      }
    });
  }

  testWidgets('shared live, scanning and loading animations are quiet when hidden', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: TickerMode(
        enabled: false,
        child: Column(children: [
          OmiActivityRing(active: true, child: SizedBox()),
          OmiLiveDot(),
          OmiBreathingDot(),
          ScanningRippleWidget(isScanning: true, size: 30),
          ShimmerWithTimeout(child: SizedBox.square(dimension: 30)),
        ]),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 100));
    debugPrint('GLOBAL hidden animations transientCallbacks=${tester.binding.transientCallbackCount}');
    expect(tester.binding.transientCallbackCount, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('shared animations stop for inactive state and shimmer timeout', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Column(children: [
        OmiActivityRing(active: false, child: SizedBox()),
        OmiLiveDot(live: false),
        OmiBreathingDot(live: false),
        ScanningRippleWidget(isScanning: false, size: 30),
        ShimmerWithTimeout(timeoutSeconds: 1, child: SizedBox.square(dimension: 30)),
      ]),
    ));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();
    debugPrint('GLOBAL inactive animations transientCallbacks=${tester.binding.transientCallbackCount}');
    expect(tester.binding.transientCallbackCount, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
