import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/ui/ui.dart';

import '../providers/guided_voice_controller_test.dart' show FakeVoiceIO;

void main() {
  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    for (final largeText in [false, true]) {
      testWidgets('$platform voice introduction stays below navigation, large text: $largeText', (tester) async {
        tester.view.physicalSize = largeText ? const Size(320, 568) : const Size(390, 844);
        tester.view.devicePixelRatio = 1;
        tester.view.padding = FakeViewPadding(top: platform == TargetPlatform.iOS ? 59 : 24, bottom: 34);
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.view.resetPadding);
        final flow = GuidedVoiceController(FakeVoiceIO());
        addTearDown(flow.dispose);
        var backs = 0;
        await tester.pumpWidget(
          MaterialApp(
            theme: buildOmiTheme().copyWith(platform: platform),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(largeText ? 2 : 1)),
              child: child!,
            ),
            home: Scaffold(
              body: OnboardingStepLayout(
                reserveHeader: true,
                onBack: () => backs++,
                progress: const OnboardingProgressDots(current: 4, total: 6),
                child: SpeechProfileWidget(controller: flow, goNext: () {}, onSkip: () {}),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final back = find.byKey(const Key('onboarding_back'));
        final title = find.text('Let Omi get to know you');
        final scroll = find.byKey(const Key('introduction_scroll'));
        final headerBottom = tester.getRect(find.byType(OnboardingProgressDots)).bottom;
        expect(tester.getRect(title).top, greaterThanOrEqualTo(headerBottom));
        expect(tester.getRect(title).overlaps(tester.getRect(back)), isFalse);
        // SafeArea is consumed by the host once; the page starts directly below its header.
        expect(tester.getRect(title).top - headerBottom, moreOrLessEquals(20));
        await tester.tap(back);
        expect(backs, 1);
        await tester.drag(scroll, const Offset(0, -350));
        await tester.pumpAndSettle();
        expect(tester.getRect(scroll).top, greaterThanOrEqualTo(headerBottom));
        expect(find.byKey(const Key('speech_profile_start')).hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('bottom-card steps retain their full-screen content and floating navigation', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: OnboardingStepLayout(
            reserveHeader: false,
            onBack: () {},
            child: const SizedBox.expand(key: Key('step_content')),
          ),
        ),
      ),
    );
    expect(tester.getRect(find.byKey(const Key('step_content'))), tester.getRect(find.byType(Scaffold)));
  });
}
