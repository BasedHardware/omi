import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'first_capture_test.dart' show host;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('capture choices and skip remain reachable at 2x text on a compact phone', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var completed = false;
    await tester.pumpWidget(host(MediaQuery(
      data: const MediaQueryData(textScaler: TextScaler.linear(2)),
      child: OnboardingCompleteScreen(onComplete: () => completed = true, emit: (_) {}, setProperty: (_, value) {}),
    )));
    final cta = find.byKey(const Key('onboarding_complete_start'));
    await tester.scrollUntilVisible(cta, 200, scrollable: find.byType(Scrollable).first);
    expect(tester.takeException(), isNull);
    await tester.tap(cta);
    expect(completed, isTrue);
  });
}
