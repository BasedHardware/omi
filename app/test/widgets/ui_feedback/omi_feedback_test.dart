import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/ui/feedback/omi_clipboard.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

import 'harness.dart';

/// OmiFeedback's contract: fixed timings, one toast at a time, Undo resolves the caller's
/// commit-or-restore decision, no close button on an undo, and a neutral surface.
void main() {
  tearDown(() {
    OmiFeedback.bottomClearance = null;
    OmiClipboard.debugSystemConfirmsCopy = null;
  });

  SnackBar shownSnackBar(WidgetTester tester) => tester.widget<SnackBar>(find.byType(SnackBar));

  group('undo', () {
    testWidgets('resolves true when Undo is tapped, after onUndo ran', (tester) async {
      var restored = false;
      bool? undone;
      await tester.pumpWidget(feedbackHarness((context) async {
        undone = await OmiFeedback.undo(context, 'Task deleted', onUndo: () => restored = true);
      }));
      await tapTrigger(tester);

      expect(shownSnackBar(tester).duration, OmiFeedbackTiming.undo);
      expect(shownSnackBar(tester).showCloseIcon, isFalse, reason: 'nothing on an undo toast destroys sooner');
      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();
      expect(restored, isTrue);
      expect(undone, isTrue);
    });

    testWidgets('resolves false when it times out', (tester) async {
      bool? undone;
      await tester.pumpWidget(feedbackHarness((context) async {
        undone = await OmiFeedback.undo(context, 'Memory deleted', onUndo: () {});
      }));
      await tapTrigger(tester);
      expect(undone, isNull);
      await tester.pump(OmiFeedbackTiming.undo + const Duration(seconds: 1));
      await tester.pumpAndSettle();
      expect(undone, isFalse);
    });

    testWidgets('resolves false when the next toast replaces it', (tester) async {
      bool? undone;
      late BuildContext captured;
      await tester.pumpWidget(feedbackHarness((context) async {
        captured = context;
        undone = await OmiFeedback.undo(context, 'Conversation deleted', onUndo: () {});
      }));
      await tapTrigger(tester);
      OmiFeedback.confirm(captured, 'Saved');
      await tester.pumpAndSettle();
      expect(undone, isFalse);
      expect(find.text('Conversation deleted'), findsNothing);
      expect(find.text('Saved'), findsOneWidget);
    });
  });

  testWidgets('timings and close button per kind', (tester) async {
    late BuildContext captured;
    await tester.pumpWidget(feedbackHarness((context) => captured = context));
    await tapTrigger(tester);

    OmiFeedback.confirm(captured, 'Copied');
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).duration, const Duration(milliseconds: 1500));
    expect(shownSnackBar(tester).showCloseIcon, isFalse);

    OmiFeedback.info(captured, 'Reconnecting');
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).duration, const Duration(seconds: 4));

    var retried = false;
    OmiFeedback.error(captured, 'Could not save', actionLabel: 'Try Again', onAction: () => retried = true);
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).duration, const Duration(seconds: 8));
    expect(shownSnackBar(tester).showCloseIcon, isTrue);
    expect(find.byType(SnackBar), findsOneWidget, reason: 'one at a time');
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(retried, isTrue);
  });

  testWidgets('neutral surface: no red/green slab behind the text', (tester) async {
    late BuildContext captured;
    await tester.pumpWidget(feedbackHarness((context) => captured = context));
    await tapTrigger(tester);
    OmiFeedback.error(captured, 'Failed');
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).backgroundColor, isNull, reason: 'the theme surface, colour lives on the icon');
    expect(shownSnackBar(tester).behavior, SnackBarBehavior.floating);
  });

  testWidgets('clears the home shell tab bar only while the shell is the visible route', (tester) async {
    late BuildContext captured;
    OmiFeedback.bottomClearance = (_) => 72;
    await tester.pumpWidget(feedbackHarness((context) => captured = context));
    await tapTrigger(tester);

    OmiFeedback.info(captured, 'On the shell');
    await tester.pumpAndSettle();
    expect((shownSnackBar(tester).margin as EdgeInsets).bottom, 12 + 72);

    Navigator.of(captured).push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: SizedBox())));
    await tester.pumpAndSettle();
    OmiFeedback.info(captured, 'On a pushed page');
    await tester.pumpAndSettle();
    expect((shownSnackBar(tester).margin as EdgeInsets).bottom, 12);
  });

  testWidgets('AppSnackbar routes through OmiFeedback on the global navigator', (tester) async {
    await tester.pumpWidget(feedbackHarness((_) {}, navigatorKey: globalNavigatorKey));
    AppSnackbar.showSnackbarError('Upload failed', duration: const Duration(milliseconds: 200));
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).duration, OmiFeedbackTiming.error, reason: 'per-call durations are ignored');
    expect(shownSnackBar(tester).backgroundColor, isNull);
    AppSnackbar.showSnackbarSuccess('Saved');
    await tester.pumpAndSettle();
    expect(shownSnackBar(tester).duration, OmiFeedbackTiming.confirm);
  });

  group('OmiClipboard', () {
    late List<String?> written;

    setUp(() {
      written = [];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.setData') written.add((call.arguments as Map)['text'] as String?);
        return null;
      });
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null);
    });

    testWidgets('empty text: nothing copied, nothing shown', (tester) async {
      bool? copied;
      await tester.pumpWidget(feedbackHarness((context) async => copied = await OmiClipboard.copy(context, '  \n')));
      await tapTrigger(tester);
      expect(copied, isFalse);
      expect(written, isEmpty);
      expect(find.byType(SnackBar), findsNothing);
    });

    testWidgets('copies and confirms with the subject', (tester) async {
      OmiClipboard.debugSystemConfirmsCopy = false;
      await tester.pumpWidget(
        feedbackHarness((context) => OmiClipboard.copy(context, 'hello', what: 'Transcript')),
      );
      await tapTrigger(tester);
      expect(written, ['hello']);
      expect(find.text('Transcript copied'), findsOneWidget);
      expect(shownSnackBar(tester).duration, OmiFeedbackTiming.confirm);
    });

    testWidgets('Android 13+: copies but lets the system chip confirm', (tester) async {
      OmiClipboard.debugSystemConfirmsCopy = true;
      await tester.pumpWidget(feedbackHarness((context) => OmiClipboard.copy(context, 'hello')));
      await tapTrigger(tester);
      expect(written, ['hello']);
      expect(find.byType(SnackBar), findsNothing);
    });
  });
}
