import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';

// Regression for #19946 review feedback: the Siri setup hint lengthened the completion
// screen's fixed Column, so at large text scales (ux-contract §16: test at 200%) the
// "Start Using Omi" button overflowed off-screen. The content is now scrollable, and
// the CTA must stay reachable. showSiriHint forces the iOS 16 App Shortcuts gate so
// the hint-rendering path is testable off-device.

const Size _compactPhone = Size(320, 568);

Widget _host(Widget child, {required double textScale}) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: MediaQuery(
      data: MediaQueryData(textScaler: TextScaler.linear(textScale)),
      child: Scaffold(body: child),
    ),
  );
}

Future<void> _pumpComplete(WidgetTester tester, {required bool showSiriHint}) async {
  tester.view.physicalSize = _compactPhone;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(_host(
      OnboardingCompleteScreen(
        onComplete: () {},
        showSiriHint: showSiriHint,
        appShortcutsAvailabilityProbe: () async => true,
      ),
      textScale: 1.0));
  // Settle the delayed entrance animation (200 ms delay + 800 ms run).
  await tester.pump(const Duration(seconds: 1));
}

void main() {
  testWidgets('completion screen keeps the start CTA reachable at 2x text with the Siri hint shown', (tester) async {
    tester.view.physicalSize = _compactPhone;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    var completed = false;
    await tester.pumpWidget(
      _host(
        OnboardingCompleteScreen(
          onComplete: () => completed = true,
          showSiriHint: true,
          appShortcutsAvailabilityProbe: () async => true,
        ),
        textScale: 2.0,
      ),
    );
    await tester.pump(const Duration(seconds: 1));

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('onboarding_siri_hint')), findsOneWidget);

    final cta = find.byKey(const Key('onboarding_complete_start'));
    await tester.scrollUntilVisible(cta, 200, scrollable: find.byType(Scrollable).first);
    expect(cta.hitTestable(), findsOneWidget);

    await tester.tap(cta.hitTestable());
    await tester.pump();
    expect(completed, isTrue);
  });

  testWidgets('completion screen without the Siri hint shows no hint key', (tester) async {
    await _pumpComplete(tester, showSiriHint: false);

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('onboarding_siri_hint')), findsNothing);
    expect(find.byKey(const Key('onboarding_complete_start')), findsOneWidget);
  });
  testWidgets('completion screen waits for App Shortcuts availability before showing the hint', (tester) async {
    final availability = Completer<bool>();
    await tester.pumpWidget(
      _host(
        OnboardingCompleteScreen(
          onComplete: () {},
          showSiriHint: true,
          appShortcutsAvailabilityProbe: () => availability.future,
        ),
        textScale: 1.0,
      ),
    );

    expect(find.byKey(const Key('onboarding_siri_hint')), findsNothing);
    await tester.pump(const Duration(seconds: 1));
    availability.complete(true);
    await tester.pump();
    expect(find.byKey(const Key('onboarding_siri_hint')), findsOneWidget);
  });

  testWidgets('completion screen hides the hint when App Shortcuts are unavailable', (tester) async {
    await tester.pumpWidget(
      _host(
        OnboardingCompleteScreen(
          onComplete: () {},
          showSiriHint: true,
          appShortcutsAvailabilityProbe: () async => false,
        ),
        textScale: 1.0,
      ),
    );
    await tester.pump(const Duration(seconds: 1));

    expect(find.byKey(const Key('onboarding_siri_hint')), findsNothing);
  });
}
