import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/widgets/home_hero.dart';

/// Paints the settled hero and reads its pixels.
///
/// Reported as "not pure white" on device while the code declares
/// [Colors.white]; this establishes whether the widget itself paints white, so
/// the search can move to the app tree instead of going in circles.
void main() {
  testWidgets('the settled headline paints pure white pixels', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          backgroundColor: Colors.black,
          body: RepaintBoundary(
            key: const ValueKey('hero'),
            child: Center(child: HomeHero(animate: false)),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const ValueKey('hero')));

    late ui.Image image;
    await tester.runAsync(() async {
      image = await boundary.toImage();
    });
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    final bytes = data!.buffer.asUint8List();

    var peak = 0;
    var fullyWhite = 0;
    for (var i = 0; i + 3 < bytes.length; i += 4) {
      final r = bytes[i];
      if (r > peak) peak = r;
      if (r >= 250 && bytes[i + 1] >= 250 && bytes[i + 2] >= 250) fullyWhite++;
    }

    // ignore: avoid_print
    print('HERO PIXELS -> peak red channel: $peak, fully-white pixels: $fullyWhite');

    expect(peak, greaterThanOrEqualTo(250), reason: 'the headline should paint pure white somewhere');
  });
}
