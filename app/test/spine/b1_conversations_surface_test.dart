import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';
import 'package:omi/pages/conversations/conversations_page.dart';

import '../support/spine/contract.dart';
import '../support/spine/widgets.dart';
import 'b1_surface_contract.dart';

void main() {
  if (const String.fromEnvironment('OMI_DEV_CONTROLS') != '1') {
    test('ordinary build does not enable B1 controls', () => expect(semanticControlsEligible, isFalse));
    return;
  }
  for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
    contractWidgets('B1 conversations on $platform', (tester) async {
      pendingContract('B1');
      F.env = Environment.dev;
      debugDefaultTargetPlatformOverride = platform;
      try {
        await checkSurface(tester, 'conversations', ConversationsPage);
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
  }
}
