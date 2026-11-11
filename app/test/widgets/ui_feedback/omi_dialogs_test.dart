import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/alerts/app_dialog.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/omi_confirm_dialog.dart';

import 'harness.dart';

/// The confirmation system: Cancel is always there, the confirm button is the caller's verb, and a
/// destructive action is marked as one — on both platforms and through every legacy adapter.
void main() {
  Color? textColor(WidgetTester tester, String label) {
    final button = tester.widget<TextButton>(find.widgetWithText(TextButton, label));
    return button.style?.foregroundColor?.resolve(<WidgetState>{});
  }

  group('showOmiConfirm', () {
    testWidgets('Material: Cancel + verb, destructive in red, resolves true only on the verb', (tester) async {
      bool? result;
      await tester.pumpWidget(feedbackHarness((context) async {
        result = await showOmiConfirm(
          context,
          title: 'Delete conversation?',
          message: 'This cannot be undone.',
          confirmLabel: 'Delete',
          destructive: true,
        );
      }));
      await tapTrigger(tester);

      expect(find.byType(AlertDialog), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
      expect(textColor(tester, 'Delete'), omiDialogDangerColor);
      expect(textColor(tester, 'Cancel'), isNot(omiDialogDangerColor));

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(result, isFalse);

      await tapTrigger(tester);
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();
      expect(result, isTrue);
    });

    testWidgets('barrier dismissal resolves false', (tester) async {
      bool? result;
      await tester.pumpWidget(feedbackHarness((context) async {
        result = await showOmiConfirm(context, title: 'Sign out?', confirmLabel: 'Sign Out');
      }));
      await tapTrigger(tester);
      await tester.tapAt(const Offset(4, 4));
      await tester.pumpAndSettle();
      expect(result, isFalse);
    });

    testWidgets('iOS: CupertinoAlertDialog with real destructive / default actions', (tester) async {
      await tester.pumpWidget(feedbackHarness(
        (context) => showOmiConfirm(context, title: 'Clear chat?', confirmLabel: 'Clear Chat', destructive: true),
        platform: TargetPlatform.iOS,
      ));
      await tapTrigger(tester);

      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.byType(TextButton), findsNothing, reason: 'no Material buttons inside a Cupertino alert');
      final actions = tester.widgetList<CupertinoDialogAction>(find.byType(CupertinoDialogAction)).toList();
      expect(actions, hasLength(2));
      final cancel = actions.first;
      final confirm = actions.last;
      expect((cancel.child as Text).data, 'Cancel');
      expect(cancel.isDefaultAction, isTrue);
      expect(confirm.isDestructiveAction, isTrue);
      expect((confirm.child as Text).data, 'Clear Chat');
    });

    testWidgets('opt-out row is one tappable target and is returned', (tester) async {
      OmiConfirmResult? result;
      await tester.pumpWidget(feedbackHarness((context) async {
        result = await showOmiConfirmWithOptOut(context, title: 'Delete?', confirmLabel: 'Delete', destructive: true);
      }));
      await tapTrigger(tester);

      final row = find.byType(OmiCheckboxRow);
      expect(tester.getSize(row).height, greaterThanOrEqualTo(44));
      await tester.tap(find.text("Don't ask me again"));
      await tester.pump();
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();
      expect(result!.confirmed, isTrue);
      expect(result!.dontAskAgain, isTrue);
    });

    testWidgets('iOS opt-out row: the box sits beside its label and shows a check once ticked', (tester) async {
      await tester.pumpWidget(feedbackHarness(
        (context) => showOmiConfirmWithOptOut(
          context,
          title: 'Delete Conversation?',
          message: 'This also deletes its memories, tasks, and audio files.',
          confirmLabel: 'Delete',
          destructive: true,
        ),
        platform: TargetPlatform.iOS,
      ));
      await tapTrigger(tester);

      expect(find.byType(CupertinoCheckbox), findsNothing);
      final box = find.byKey(const ValueKey('omi_checkbox_box'));
      final label = find.text("Don't ask me again");
      expect(tester.getSize(box), const Size(18, 18));
      expect(tester.getTopLeft(label).dx - tester.getTopRight(box).dx, lessThanOrEqualTo(10),
          reason: 'no loose gap between the box and its label');
      expect(find.byIcon(Icons.check_rounded), findsNothing);

      await tester.tap(label);
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
    });

    group('the opt-out confirm is Omi\'s card', () {
      Future<void> pumpDelete(WidgetTester tester, Size screen, {double textScale = 1}) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = screen;
        tester.platformDispatcher.textScaleFactorTestValue = textScale;
        addTearDown(tester.view.reset);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await tester.pumpWidget(feedbackHarness(
          (context) => showOmiConfirmWithOptOut(
            context,
            title: 'Delete Conversation?',
            message: 'This also deletes its memories, tasks, and audio files.',
            confirmLabel: 'Delete',
            destructive: true,
          ),
          platform: TargetPlatform.iOS,
        ));
        await tapTrigger(tester);
      }

      double cardWidth(WidgetTester tester) =>
          tester.getSize(find.descendant(of: find.byType(OmiDialogCard), matching: find.byType(Material)).first).width;

      testWidgets('not the fixed-width system alert: its width follows the screen, up to 400pt', (tester) async {
        await pumpDelete(tester, const Size(390, 844));
        expect(find.byType(CupertinoAlertDialog), findsNothing);
        expect(cardWidth(tester), 390 - 2 * 32);

        await pumpDelete(tester, const Size(1024, 1366));
        expect(cardWidth(tester), OmiDialogCard.maxWidth);
      });

      testWidgets('Cancel and Delete sit side by side, and stack with Delete on top at large text', (tester) async {
        final cancel = find.widgetWithText(TextButton, 'Cancel');
        final delete = find.widgetWithText(TextButton, 'Delete');
        TextStyle? labelStyle(String label) => tester.widget<Text>(find.text(label)).style;

        await pumpDelete(tester, const Size(430, 932));
        expect(tester.getTopLeft(cancel).dy, tester.getTopLeft(delete).dy);
        expect(tester.getTopLeft(cancel).dx, lessThan(tester.getTopLeft(delete).dx));
        // Plain text buttons, no fills: Delete red, Cancel the bold default.
        expect(textColor(tester, 'Delete'), omiDialogDangerColor);
        expect(tester.widget<TextButton>(delete).style?.backgroundColor?.resolve(<WidgetState>{}), isNull);
        expect(labelStyle('Cancel')?.fontWeight, FontWeight.w600);
        expect(labelStyle('Delete')?.fontWeight, FontWeight.w400);

        await pumpDelete(tester, const Size(430, 932), textScale: 2);
        expect(tester.getTopLeft(delete).dy, lessThan(tester.getTopLeft(cancel).dy));
        expect(tester.takeException(), isNull, reason: 'no overflow at 200%');
      });

      testWidgets('the row sits with the message, with more air before the buttons', (tester) async {
        await pumpDelete(tester, const Size(430, 932));
        final message = tester.getRect(find.text('This also deletes its memories, tasks, and audio files.'));
        final box = tester.getRect(find.byKey(const ValueKey('omi_checkbox_box')));
        final buttons = tester.getRect(find.widgetWithText(TextButton, 'Cancel'));
        final above = box.top - message.bottom;
        final below = buttons.top - box.bottom;
        expect(above, inInclusiveRange(12, 22));
        expect(below, inInclusiveRange(20, 30));
        expect(above, lessThan(below));
        expect(tester.getSize(find.byType(OmiCheckboxRow)).height, greaterThanOrEqualTo(44));
      });
    });
  });

  group('showOmiConfirmMenu', () {
    Future<OmiConfirmResult?> Function() pumpMenu(WidgetTester tester, Rect anchor, {double textScale = 1}) {
      OmiConfirmResult? result;
      tester.platformDispatcher.textScaleFactorTestValue = textScale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      return () async {
        await tester.pumpWidget(feedbackHarness((context) async {
          result = await showOmiConfirmMenu(
            context,
            anchor: anchor,
            title: 'Delete Conversation?',
            message: 'This also deletes its memories, tasks, and audio files.',
            confirmLabel: 'Delete Conversation',
            offerOptOut: true,
          );
        }));
        await tapTrigger(tester);
        return result;
      };
    }

    final confirm = find.byKey(const ValueKey('omi_confirm_menu_confirm'));

    testWidgets('opens below its anchor, trailing edges lined up', (tester) async {
      const anchor = Rect.fromLTWH(720, 60, 44, 44);
      await pumpMenu(tester, anchor)();
      final item = tester.getRect(confirm);
      expect(item.top, greaterThan(anchor.bottom));
      expect(item.right, anchor.right);
      expect(item.width, 268);
      expect(tester.getSize(confirm).height, greaterThanOrEqualTo(44));
      expect(find.byType(OmiDialogCard), findsNothing);
    });

    testWidgets('opens above an anchor near the bottom of the screen', (tester) async {
      const anchor = Rect.fromLTWH(720, 520, 44, 44);
      await pumpMenu(tester, anchor)();
      expect(tester.getRect(confirm).bottom, lessThan(anchor.top));
    });

    testWidgets('a tap outside cancels; the toggle and the action confirm with the opt-out', (tester) async {
      const anchor = Rect.fromLTWH(720, 60, 44, 44);
      var result = pumpMenu(tester, anchor);
      await result();
      await tester.tapAt(const Offset(10, 500));
      await tester.pumpAndSettle();
      expect(confirm, findsNothing);
      expect((await result())!.confirmed, isFalse);
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.check_rounded), findsNothing);
      await tester.tap(find.text("Don't ask me again"));
      await tester.pump();
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      final confirmed = await result();
      expect(confirmed!.confirmed, isTrue);
      expect(confirmed.dontAskAgain, isTrue);
    });

    testWidgets('at large text sizes it falls back to the card', (tester) async {
      await pumpMenu(tester, const Rect.fromLTWH(720, 60, 44, 44), textScale: 1.6)();
      expect(confirm, findsNothing);
      expect(find.byType(OmiDialogCard), findsOneWidget);
      expect(find.text('Delete Conversation'), findsOneWidget);
    });
  });

  testWidgets('showOmiAlert has one OK button', (tester) async {
    await tester.pumpWidget(feedbackHarness((context) => showOmiAlert(context, title: 'Saved', message: 'Done.')));
    await tapTrigger(tester);
    expect(find.byType(TextButton), findsOneWidget);
    expect(find.text('OK'), findsOneWidget);
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
  });

  group('legacy adapters', () {
    testWidgets('ConfirmationDialog shows Cancel without cancelText, and Cancel closes even with a no-op onCancel',
        (tester) async {
      await tester.pumpWidget(feedbackHarness((context) {
        showDialog(
          context: context,
          builder: (c) => ConfirmationDialog(
            title: 'Finished conversation?',
            description: 'Stop recording and summarize?',
            confirmText: 'Stop',
            onConfirm: () => Navigator.pop(c),
            onCancel: () {},
          ),
        );
      }));
      await tapTrigger(tester);
      expect(find.text('Cancel'), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
    });

    testWidgets('ConfirmationDialog checkbox label is tappable', (tester) async {
      bool? checked;
      await tester.pumpWidget(feedbackHarness((context) {
        showDialog(
          context: context,
          builder: (c) => ConfirmationDialog(
            title: 'Submit app?',
            description: 'It goes to review.',
            checkboxText: "Don't show again",
            onCheckboxChanged: (v) => checked = v,
            onConfirm: () => Navigator.pop(c),
            onCancel: () => Navigator.pop(c),
          ),
        );
      }));
      await tapTrigger(tester);
      expect(find.byType(OmiDialogCard), findsOneWidget, reason: 'a dialog with a control is the card');
      await tester.tap(find.text("Don't show again"));
      await tester.pump();
      expect(checked, isTrue);
    });

    testWidgets('OmiConfirmDialog uses localized defaults and infers destructive from colour', (tester) async {
      bool? result;
      await tester.pumpWidget(feedbackHarness((context) async {
        result = await OmiConfirmDialog.show(context, title: 'Delete recording?', message: 'Gone for good.');
      }));
      await tapTrigger(tester);
      expect(find.text('Cancel'), findsOneWidget);
      expect(find.text('Confirm'), findsOneWidget);
      expect(textColor(tester, 'Confirm'), omiDialogDangerColor);
      await tester.tap(find.text('Confirm'));
      await tester.pumpAndSettle();
      expect(result, isTrue);

      await tester.pumpWidget(feedbackHarness((context) {
        OmiConfirmDialog.show(context,
            title: 'Sync?', message: 'Upload now.', confirmLabel: 'Sync', confirmColor: Colors.white);
      }));
      await tapTrigger(tester);
      expect(textColor(tester, 'Sync'), isNot(omiDialogDangerColor));
    });

    testWidgets('AppDialog.show honours singleButton and closes after the callback', (tester) async {
      var cancelled = 0;
      await tester.pumpWidget(feedbackHarness(
        (_) => AppDialog.show(
            title: 'Error', content: 'Could not update.', singleButton: true, onCancel: () => cancelled++),
        navigatorKey: globalNavigatorKey,
      ));
      await tapTrigger(tester);
      expect(find.byType(TextButton), findsOneWidget);
      expect(find.text('Cancel'), findsNothing);
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      expect(cancelled, 1);
      expect(find.byType(AlertDialog), findsNothing);
    });
  });
}
