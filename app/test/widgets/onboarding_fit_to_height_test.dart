import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/onboarding_layout.dart';

const _longCopy =
    'By continuing, your conversations, recordings, and personal information will be securely stored on our '
    'servers. Your audio recordings and transcripts are processed by third-party AI services to provide you '
    'with AI-powered insights and enable all app features. '
    'This sentence repeats so the block is taller than the space it is given. '
    'This sentence repeats so the block is taller than the space it is given. '
    'This sentence repeats so the block is taller than the space it is given.';

Future<void> _pump(WidgetTester tester, {required double maxHeight, required String copy}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Align(
          alignment: Alignment.bottomCenter,
          child: SizedBox(
            width: 320,
            height: maxHeight,
            child: OnboardingFitToHeight(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Data & Privacy', style: TextStyle(fontSize: 28)),
                  Text(copy, key: const Key('copy'), style: const TextStyle(fontSize: 14)),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
  // Post-frame measurement, then the rebuild(s) it triggers.
  for (var i = 0; i < 6; i++) {
    await tester.pump();
  }
}

double _scaleOf(WidgetTester tester) {
  final context = tester.element(find.byKey(const Key('copy')));
  return MediaQuery.of(context).textScaler.scale(1.0);
}

void main() {
  testWidgets('copy that fits keeps its natural text size', (tester) async {
    await _pump(tester, maxHeight: 400, copy: 'Short.');
    expect(_scaleOf(tester), 1.0);
  });

  testWidgets('copy that overflows shrinks its text scale until it fits, at full width', (tester) async {
    await _pump(tester, maxHeight: 120, copy: _longCopy);

    final scale = _scaleOf(tester);
    expect(scale, lessThan(1.0));
    expect(scale, greaterThanOrEqualTo(0.6));

    final copyBox = tester.renderObject<RenderBox>(find.byKey(const Key('copy')));
    expect(copyBox.size.width, 320);
    // Nothing scrolls: no scroll view is part of the fit.
    expect(find.byType(SingleChildScrollView), findsNothing);
  });

  testWidgets('copy grows back toward its natural size when it is given more height', (tester) async {
    await _pump(tester, maxHeight: 120, copy: _longCopy);
    final shrunk = _scaleOf(tester);
    expect(shrunk, lessThan(1.0));

    await _pump(tester, maxHeight: 2000, copy: _longCopy);
    expect(_scaleOf(tester), 1.0);
  });
}
