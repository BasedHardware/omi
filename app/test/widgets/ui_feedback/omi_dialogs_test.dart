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
