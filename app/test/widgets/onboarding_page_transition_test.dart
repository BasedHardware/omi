import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/widgets/onboarding_page_transition.dart';

class _DisposeProbe extends StatefulWidget {
  const _DisposeProbe({required this.onDispose});

  final VoidCallback onDispose;

  @override
  State<_DisposeProbe> createState() => _DisposeProbeState();
}

class _DisposeProbeState extends State<_DisposeProbe> {
  @override
  void dispose() {
    widget.onDispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const Text('probe');
}

void main() {
  test('default fade is short enough that consent-to-name does not linger', () {
    const transition = OnboardingPageTransition(pageKey: 0, child: SizedBox());
    expect(transition.duration, kOnboardingPageFadeDuration);
    expect(kOnboardingPageFadeDuration, const Duration(milliseconds: 400));
  });

  testWidgets('changing entryDelay on the same pageKey does not dispose the child', (tester) async {
    var disposes = 0;

    Widget page({required Duration entryDelay}) {
      return OnboardingPageTransition(
        pageKey: 9,
        entryDelay: entryDelay,
        child: _DisposeProbe(onDispose: () => disposes++),
      );
    }

    await tester.pumpWidget(MaterialApp(home: page(entryDelay: const Duration(milliseconds: 2200))));
    expect(find.text('probe'), findsOneWidget);
    expect(disposes, 0);

    // Speech-profile Get Started used to flip delay to zero, remount the
    // step, and SpeechProfileWidget.close() reset startedRecording.
    await tester.pumpWidget(MaterialApp(home: page(entryDelay: Duration.zero)));
    await tester.pump();

    expect(find.text('probe'), findsOneWidget);
    expect(disposes, 0);
  });

  testWidgets('a new pageKey still replaces the previous child', (tester) async {
    var disposes = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: OnboardingPageTransition(
          pageKey: 8,
          child: _DisposeProbe(onDispose: () => disposes++),
        ),
      ),
    );

    await tester.pumpWidget(
      const MaterialApp(
        home: OnboardingPageTransition(
          pageKey: 9,
          child: Text('next'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(disposes, 1);
    expect(find.text('next'), findsOneWidget);
  });
}
