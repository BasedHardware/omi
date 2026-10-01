/// The update pop-up (#20039): Omi's own words in every locale instead of the `upgrader` package's
/// ("…is now available-you have…"), a short What's New from the store notes, and a required update
/// with no Not Now.
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/widgets/upgrade_alert.dart';

import 'ui_feedback/harness.dart';

void main() {
  Future<({int updates, int laters})> show(WidgetTester tester, {bool required = false, String? notes}) async {
    var updates = 0;
    var laters = 0;
    await tester.pumpWidget(feedbackHarness(
      (context) => showDialog<void>(
        context: context,
        builder: (_) => UpdatePrompt(
          required: required,
          releaseNotes: notes,
          onUpdate: () => updates++,
          onLater: () => laters++,
        ),
      ),
      platform: TargetPlatform.iOS,
    ));
    await tapTrigger(tester);
    return (updates: updates, laters: laters);
  }

  testWidgets('an update offers Not Now and Update in Omi\'s words', (tester) async {
    await show(tester);
    expect(find.text('Update available'), findsOneWidget);
    expect(find.text('A new version of Omi is ready, with fixes and improvements.'), findsOneWidget);
    expect(find.textContaining('available-you'), findsNothing);
    expect(find.textContaining('Version'), findsNothing, reason: 'no version numbers');
    final actions = tester.widgetList<CupertinoDialogAction>(find.byType(CupertinoDialogAction)).toList();
    expect(actions.map((a) => (a.child as Text).data), ['Not Now', 'Update']);
    expect(actions.last.isDefaultAction, isTrue);
    expect(find.byKey(const ValueKey('update_whats_new')), findsNothing, reason: 'no notes, no What\'s New');
  });

  testWidgets('a required update has one way on: Update', (tester) async {
    await show(tester, required: true);
    expect(find.text('Update required'), findsOneWidget);
    expect(
        find.text('This version of Omi is no longer supported. Update to keep recording and syncing.'), findsOneWidget);
    expect(find.text('Not Now'), findsNothing);
    expect(find.byKey(const ValueKey('update_now')), findsOneWidget);
  });

  testWidgets('store notes add a two-line What\'s New', (tester) async {
    await show(tester, notes: '• Faster sync for long recordings\n\n- Fixes for Bluetooth reconnects\n• A third line');
    expect(find.byKey(const ValueKey('update_whats_new')), findsOneWidget);
    expect(find.text("What's New"), findsOneWidget);
    expect(find.text('Faster sync for long recordings\nFixes for Bluetooth reconnects'), findsOneWidget);
    expect(find.textContaining('A third line'), findsNothing);
  });

  test('release notes reduce to their first two non-empty lines, markers dropped', () {
    expect(UpdateWhatsNew.fromReleaseNotes(null), isNull);
    expect(UpdateWhatsNew.fromReleaseNotes('  \n \n'), isNull);
    expect(UpdateWhatsNew.fromReleaseNotes('* One\n– Two\nThree'), 'One\nTwo');
  });
}
