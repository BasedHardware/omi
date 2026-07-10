import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/meta_glasses_onboarding_step.dart';
import 'package:omi/providers/meta_wearables_provider.dart';

void main() {
  testWidgets('onboarding device step renders a Meta Glasses option', (tester) async {
    var metaTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: ChangeNotifierProvider(
          create: (_) => MetaWearablesProvider(),
          child: OnboardingMetaGlassesStep(
            onMetaGlassesSelected: () => metaTapped = true,
            onOmiDeviceSelected: () {},
            onContinueWithoutDevice: () {},
          ),
        ),
      ),
    );

    await tester.pump();

    expect(find.byKey(const Key('onboarding_meta_glasses_option')), findsOneWidget);
    expect(find.text('Meta Glasses'), findsOneWidget);
    await tester.tap(find.byKey(const Key('onboarding_meta_glasses_option')));
    expect(metaTapped, isTrue);
  });

  test('registered linked Meta glasses satisfy onboarding device completion', () {
    final provider = MetaWearablesProvider()
      ..registrationState = RegistrationState.registered
      ..devices = const [
        DeviceInfo(
          uuid: 'rayban-1',
          name: 'Ray-Ban Meta',
          kind: DeviceKind.rayBanMeta,
          linkState: DeviceLinkState.connected,
        ),
      ];

    expect(metaGlassesOnboardingComplete(provider), isTrue);
  });
}
