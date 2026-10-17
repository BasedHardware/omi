import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_navigation_chrome.dart';

import '../../../integration_test/support/native_host_harness.dart';
import 'native_test_host.dart';

Widget _surface(String title, {String save = 'Save'}) =>
    IosNativeSurface(title: title, fallback: Text(title), toolbar: [
      NativeRow('save', save, action: (_) {})
    ], sections: [
      NativeSection('editor', [NativeRow('draft', 'Description', kind: 'text', value: title, action: (_) {})])
    ]);

void main() {
  testWidgets('nativeProjectedRow finds the rows a surface dispatches, chrome included, topmost route last',
      (tester) async {
    NativeTestHost.install();
    await tester.pumpWidget(NativeTestHost.app(NativeNavigationChrome(toolbar: [
      NativeRow('onboarding_back', 'Back', symbol: 'chevron.backward', action: (_) {})
    ], sections: const [
      NativeSection('steps', [NativeRow('onboarding_step', 'Step 1 of 3', kind: 'label')])
    ], child: _surface('First'))));
    await NativeTestHost.settle(tester);
    expect(nativeProjectedRow(tester, 'onboarding_back').title, 'Back');
    expect(nativeProjectedRow(tester, 'onboarding_step').title, 'Step 1 of 3');
    expect(nativeProjectedRow(tester, 'draft').value, 'First');
    expect(() => nativeProjectedRow(tester, 'missing'), throwsA(isA<TestFailure>()));

    // A pushed route projecting the same ids wins over the offstage route beneath it.
    unawaited(Navigator.of(tester.element(find.byType(IosNativeSurface)))
        .push(MaterialPageRoute<void>(builder: (_) => _surface('Second', save: 'Done'))));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(seconds: 1));
    expect(nativeProjectedRow(tester, 'save').title, 'Done');
    expect(nativeProjectedRow(tester, 'draft').value, 'Second');
    expect(nativeProjectedRow(tester, 'onboarding_back').title, 'Back', reason: 'Offstage routes are searched too');
    expect(tester.takeException(), isNull);
  });
}
