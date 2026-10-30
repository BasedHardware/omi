/// The update prompt (#20039): an Omi sheet in Omi's own words in every locale, instead of the
/// `upgrader` package's ("…is now available-you have…"), with the app icon, a short What's New from
/// the store notes, then Update and Not Now. A required update has no Not Now and no handle, and
/// nothing dismisses it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/widgets/upgrade_alert.dart';

import 'ui_feedback/harness.dart';

void main() {
  late List<String> calls;
  final sheet = find.byType(BottomSheet);
  final update = find.byKey(const ValueKey('update_now'));
  final later = find.byKey(const ValueKey('update_not_now'));

  Future<void> show(WidgetTester tester, {bool required = false, String? notes}) async {
    calls = [];
    await tester.pumpWidget(feedbackHarness(
      (context) => showUpdatePrompt(
        context,
        required: required,
        releaseNotes: notes,
        onUpdate: () => calls.add('update'),
        onLater: () => calls.add('later'),
      ),
      platform: TargetPlatform.iOS,
    ));
    await tapTrigger(tester);
  }

  testWidgets('an update is a sheet in Omi\'s words: Update over Not Now', (tester) async {
    await show(tester);
    expect(sheet, findsOneWidget);
    expect(tester.widget<BottomSheet>(sheet).showDragHandle, isTrue);
    expect(find.text('Update available'), findsOneWidget);
    expect(find.text('A new version of Omi is ready, with fixes and improvements.'), findsOneWidget);
    expect(find.textContaining('available-you'), findsNothing);
    expect(find.textContaining('Version'), findsNothing, reason: 'no version numbers');
    expect(tester.widget<OmiButton>(update).variant, OmiButtonVariant.primary);
    expect(tester.widget<OmiButton>(later).variant, OmiButtonVariant.tertiary);
    expect(tester.getTopLeft(update).dy, lessThan(tester.getTopLeft(later).dy));
    expect(find.byKey(const ValueKey('update_whats_new')), findsNothing, reason: 'no notes, no What\'s New');
  });

  testWidgets('Update and Not Now close the sheet and report; a tap outside counts as Not Now', (tester) async {
    await show(tester);
    await tester.tap(update);
    await tester.pumpAndSettle();
    expect(sheet, findsNothing);
    expect(calls, ['update']);

    await show(tester);
    await tester.tap(later);
    await tester.pumpAndSettle();
    expect(sheet, findsNothing);
    expect(calls, ['later']);

    await show(tester);
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    expect(sheet, findsNothing);
    expect(calls, ['later']);
  });

  testWidgets('a required update: Update only, no handle, and nothing closes it', (tester) async {
    await show(tester, required: true);
    expect(find.text('Update required'), findsOneWidget);
    expect(
        find.text('This version of Omi is no longer supported. Update to keep recording and syncing.'), findsOneWidget);
    expect(later, findsNothing);
    expect(tester.widget<BottomSheet>(sheet).showDragHandle, isFalse);

    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    await tester.drag(find.text('Update required'), const Offset(0, 400));
    await tester.pumpAndSettle();
    expect(sheet, findsOneWidget, reason: 'neither the scrim nor a swipe closes it');

    await tester.tap(update);
    await tester.pumpAndSettle();
    expect(calls, ['update']);
    expect(sheet, findsOneWidget, reason: 'it stays until the new version takes over');
  });

  testWidgets('store notes add a two-line What\'s New, one bullet a line', (tester) async {
    await show(tester, notes: '• Faster sync for long recordings\n\n- Fixes for Bluetooth reconnects\n• A third line');
    expect(find.byKey(const ValueKey('update_whats_new')), findsOneWidget);
    expect(find.text("What's New"), findsOneWidget);
    expect(find.text('Faster sync for long recordings'), findsOneWidget);
    expect(find.text('Fixes for Bluetooth reconnects'), findsOneWidget);
    expect(find.textContaining('A third line'), findsNothing);
  });

  test('release notes reduce to their first two non-empty lines, markers dropped', () {
    expect(UpdateWhatsNew.fromReleaseNotes(null), isNull);
    expect(UpdateWhatsNew.fromReleaseNotes('  \n \n'), isNull);
    expect(UpdateWhatsNew.fromReleaseNotes('* One\n– Two\nThree'), 'One\nTwo');
  });
}
