import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/ui/omi_tokens.dart';

// The pendant tutorial steps sit on a surface1 → surface0 gradient. Their shared
// scaffold used to hard-code white text and a white button, which vanished on the
// light palette (white-on-white on the last tutorial steps).
void main() {
  tearDown(() => OmiColors.active = OmiPalette.light);

  for (final palette in [OmiPalette.light, OmiPalette.dark]) {
    final name = palette == OmiPalette.light ? 'light' : 'dark';

    testWidgets('step title, subtitle and Continue follow the $name palette', (tester) async {
      OmiColors.active = palette;
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          backgroundColor: palette.surface0,
          body: OnboardingStepScaffold(
            title: 'Step title',
            subtitle: 'Step subtitle',
            content: const SizedBox.shrink(),
            bottomAction: OnboardingContinueButton(onPressed: () {}),
          ),
        ),
      ));

      final title = tester.widget<Text>(find.text('Step title'));
      expect(title.style!.color, palette.textPrimary);
      expect(title.style!.color, isNot(palette.surface0));
      expect(title.style!.color, isNot(palette.surface1));

      final subtitle = tester.widget<Text>(find.text('Step subtitle'));
      expect(subtitle.style!.color, palette.textSecondary);

      final button = tester.widget<ElevatedButton>(find.byType(ElevatedButton));
      final background = button.style!.backgroundColor!.resolve(<WidgetState>{});
      final foreground = button.style!.foregroundColor!.resolve(<WidgetState>{});
      expect(background, palette.accent);
      expect(foreground, palette.onAccent);
      expect(background, isNot(palette.surface0));
    });
  }
}
