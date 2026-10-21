import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';
import 'package:omi/pages/onboarding/wrapper.dart';

import '../support/spine/contract.dart';
import '../support/spine/widgets.dart';
import 'b1_surface_contract.dart';

void main() {
  if (const String.fromEnvironment('OMI_DEV_CONTROLS') != '1') {
    test('ordinary build does not enable B1 controls', () => expect(semanticControlsEligible, isFalse));
    return;
  }
  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    contractWidgets('B1 onboarding on $platform', (tester) async {
      pendingContract('B1');
      F.env = Environment.dev;
      debugDefaultTargetPlatformOverride = platform;
      try {
        await checkSurface(tester, 'onboarding', OnboardingWrapper);
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
  }
}
