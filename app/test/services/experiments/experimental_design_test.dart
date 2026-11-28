import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/experimental_design.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ExperimentalDesign.debugOverride = null;
    ExperimentalDesign.debugSetFlag(false);
  });

  tearDown(() {
    ExperimentalDesign.debugSetFlag(false);
    ExperimentalDesign.manual = false;
  });

  test('off by default; on by the Developer Settings choice, which is saved', () {
    expect(ExperimentalDesign.enabled, isFalse);
    ExperimentalDesign.manual = true;
    expect(ExperimentalDesign.enabled, isTrue);
    expect(SharedPreferencesUtil().getBool(ExperimentalDesign.prefKey), isTrue);
    ExperimentalDesign.manual = false;
    expect(ExperimentalDesign.enabled, isFalse);
  });

  test('the flag turns it on whatever the saved choice, and off again when it goes', () {
    ExperimentalDesign.debugSetFlag(true);
    expect(ExperimentalDesign.enabled, isTrue);
    expect(ExperimentalDesign.byFlag, isTrue);
    expect(ExperimentalDesign.manual, isFalse);
    ExperimentalDesign.debugSetFlag(false);
    expect(ExperimentalDesign.enabled, isFalse);
  });

  testWidgets('a widget under the scope rebuilds when the answer changes', (tester) async {
    await tester.pumpWidget(ExperimentalDesignScope(
      child: Builder(
        builder: (context) => Text(ExperimentalDesign.of(context) ? 'new' : 'old', textDirection: TextDirection.ltr),
      ),
    ));
    expect(find.text('old'), findsOneWidget);
    ExperimentalDesign.manual = true;
    await tester.pump();
    expect(find.text('new'), findsOneWidget);
    ExperimentalDesign.debugSetFlag(true);
    ExperimentalDesign.manual = false;
    await tester.pump();
    expect(find.text('new'), findsOneWidget, reason: 'the flag keeps it on');
  });
}
