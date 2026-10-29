import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/account_deletion.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/restore_account.dart';
import 'package:omi/ui/ui.dart';

Widget deletionTestHost(Widget child) => MaterialApp(
      theme: buildOmiTheme(brightness: Brightness.light),
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en')],
      home: child,
    );

Future<void> confirmStep(WidgetTester tester, DeletionPendingData data) async {
  await tester.pumpWidget(deletionTestHost(DeleteAccount(loadPendingData: () async => data)));
  await tester.tap(find.text('Privacy concerns'));
  await tester.pump();
  await tester.tap(find.text('Continue'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Continue'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => OmiColors.active = OmiColors.forBrightness(Brightness.light));

  testWidgets('grace keeps server recordings and delays erasure; only phone audio warns of loss', (tester) async {
    await confirmStep(tester, const DeletionPendingData(processingCount: 14, notUploadedCount: 3, gracePeriodDays: 14));
    expect(find.textContaining('14 recordings are still processing. They’re kept with your account for 14 days.'),
        findsOneWidget);
    expect(find.textContaining("3 recordings haven't uploaded yet. Deleting now loses them"), findsOneWidget);
    expect(find.text('Your memories and conversations will be erased after 14 days.'), findsOneWidget);
    expect(find.text('Sign in again within 14 days to restore your account.'), findsOneWidget);
    expect(find.textContaining('Deleting now loses'), findsOneWidget);
    expect(find.text('Your apps and integrations disconnect immediately.'), findsOneWidget);
    expect(find.text('Your subscription is cancelled immediately.'), findsOneWidget);
  });

  testWidgets('no policy means immediate loss for processing and phone audio, no restore promise', (tester) async {
    await confirmStep(tester, const DeletionPendingData(processingCount: 2, notUploadedCount: 1, gracePeriodDays: 0));
    expect(find.textContaining('recordings still processing. Deleting now loses them.'), findsOneWidget);
    expect(find.textContaining("1 recording hasn't uploaded yet. Deleting now loses it"), findsOneWidget);
    expect(find.textContaining('Sign in again within'), findsNothing);
    expect(find.textContaining('will be erased after'), findsNothing);
  });

  testWidgets('server-only grace never warns that recordings are lost immediately', (tester) async {
    await confirmStep(tester, const DeletionPendingData(processingCount: 1, notUploadedCount: 0, gracePeriodDays: 7));
    expect(find.textContaining('kept with your account for 7 days'), findsOneWidget);
    expect(find.textContaining('Deleting now loses'), findsNothing);
  });

  testWidgets('one-day backend policy uses singular retention and erasure copy', (tester) async {
    await confirmStep(tester, const DeletionPendingData(processingCount: 1, notUploadedCount: 0, gracePeriodDays: 1));
    expect(find.textContaining('kept with your account for 1 day.'), findsOneWidget);
    expect(find.text('Your memories and conversations will be erased after 1 day.'), findsOneWidget);
    expect(find.textContaining('Deleting now loses'), findsNothing);
  });

  for (final reason in ['Just taking a break', 'Too many technical issues']) {
    testWidgets('$reason pause awaits capture then leaves the flow', (tester) async {
      final paused = Completer<void>();
      var calls = 0;
      await tester.pumpWidget(deletionTestHost(Builder(
          builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                          builder: (_) => DeleteAccount(pauseRecording: () {
                            calls++;
                            return paused.future;
                          }),
                        )),
                    child: const Text('Open')),
              ))));
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text(reason));
      await tester.pump();
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Your subscription continues unchanged.'), findsOneWidget);
      await tester.tap(find.byKey(const Key('delete_pause_omi')));
      await tester.pump();
      expect(calls, 1);
      expect(find.text('Pause Omi Instead?'), findsOneWidget);
      paused.complete();
      await tester.pumpAndSettle();
      expect(find.text('Open'), findsOneWidget);
      expect(find.text('Pause Omi Instead?'), findsNothing);
    });
  }

  testWidgets('pause failure keeps the user on the choice screen; continue still works', (tester) async {
    await tester.pumpWidget(deletionTestHost(DeleteAccount(pauseRecording: () async => throw StateError('capture'))));
    await tester.tap(find.text('Just taking a break'));
    await tester.pump();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('delete_pause_omi')));
    await tester.pumpAndSettle();
    expect(find.text('Pause Omi Instead?'), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('delete_continue_deleting')));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('restore requires server success; finish is a separate explicit choice', (tester) async {
    var restored = 0;
    var calls = 0;
    await tester.pumpWidget(deletionTestHost(RestoreAccount(
      status:
          AccountDeletionStatus(pendingDeletion: true, wipeAt: DateTime.now().add(const Duration(days: 7, hours: 1))),
      restore: () async {
        calls++;
        return calls == 1 ? const ApiFailure(ApiProblem(ApiProblemKind.server)) : const ApiSuccess(true);
      },
      onRestored: () => restored++,
      onFinished: () {},
    )));
    expect(find.text('Restore my account'), findsOneWidget);
    expect(find.text('Finish deleting'), findsOneWidget);
    await tester.tap(find.byKey(const Key('restore_my_account')));
    await tester.pumpAndSettle();
    expect(restored, 0);
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('finish_deleting')));
    await tester.pumpAndSettle();
    expect(find.text('Erase my account now'), findsOneWidget);
    expect(find.textContaining('This ends the restore window.'), findsNothing);
    await tester.tap(find.byKey(const Key('finish_deleting_confirm')));
    await tester.pumpAndSettle();
    expect(find.textContaining('This ends the restore window.'), findsOneWidget);
    expect(find.text('Erase Your Account?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.textContaining('This ends the restore window.'), findsNothing);
    await tester.tap(find.byKey(const Key('restore_my_account')));
    await tester.pumpAndSettle();
    expect(restored, 1);
  });

  testWidgets('restore deadline copy uses whole wipe_at days and hides unknown or expired deadlines', (tester) async {
    final now = DateTime.now();

    Future<void> show(AccountDeletionStatus status) async {
      await tester.pumpWidget(deletionTestHost(RestoreAccount(
        status: status,
        onRestored: () {},
        onFinished: () {},
      )));
      await tester.pumpAndSettle();
    }

    await show(AccountDeletionStatus(pendingDeletion: true, wipeAt: now.add(const Duration(days: 9, hours: 1))));
    expect(find.text('You have 9 days left to restore your account.'), findsOneWidget);
    expect(find.textContaining('14 days'), findsNothing);

    await show(AccountDeletionStatus(pendingDeletion: true, wipeAt: now.add(const Duration(days: 1, hours: 1))));
    expect(find.text('You have 1 day left to restore your account.'), findsOneWidget);

    await show(AccountDeletionStatus(pendingDeletion: true, wipeAt: now.add(const Duration(hours: 23))));
    expect(find.text('You have less than a day left to restore your account.'), findsOneWidget);

    await show(const AccountDeletionStatus(pendingDeletion: true, gracePeriodDays: 14));
    expect(find.textContaining('left to restore your account'), findsNothing);

    await show(AccountDeletionStatus(pendingDeletion: true, wipeAt: now.subtract(const Duration(minutes: 1))));
    expect(find.textContaining('left to restore your account'), findsNothing);
  });

  testWidgets('finish deletion puts progress on erase, leaves restore idle, and retains errors', (tester) async {
    final response = Completer<ApiResult<bool>>();
    var calls = 0;
    await tester.pumpWidget(deletionTestHost(RestoreAccount(
      status: const AccountDeletionStatus(pendingDeletion: true),
      finish: () {
        calls++;
        return response.future;
      },
      onRestored: () {},
      onFinished: () {},
    )));
    await tester.tap(find.byKey(const Key('finish_deleting')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('finish_deleting_confirm')));
    await tester.pumpAndSettle();
    expect(calls, 0);
    await tester.tap(find.text('Erase my account now').last);
    await tester.pump();
    expect(calls, 1);
    expect(tester.widget<OmiButton>(find.byKey(const Key('finish_deleting_confirm'))).isLoading, isTrue);
    expect(tester.widget<OmiButton>(find.byKey(const Key('restore_my_account'))).isLoading, isFalse);
    response.complete(const ApiFailure(ApiProblem(ApiProblemKind.server)));
    await tester.pumpAndSettle();
    expect(find.text('Erase my account now'), findsOneWidget);
    expect(calls, 1);
  });

  testWidgets('pending gate never builds product; failed status offers retry', (tester) async {
    var productBuilds = 0;
    var checks = 0;
    await tester.pumpWidget(deletionTestHost(AccountDeletionGate(
      check: ({bool refresh = false}) async {
        checks++;
        return checks == 1
            ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
            : const ApiSuccess(AccountDeletionStatus(pendingDeletion: true));
      },
      productBuilder: (_) {
        productBuilds++;
        return const Text('Product');
      },
      onFinished: () {},
      onRestored: () {},
    )));
    await tester.pumpAndSettle();
    expect(productBuilds, 0);
    await tester
        .tap(find.descendant(of: find.byKey(const Key('deletion_status_retry')), matching: find.byType(OmiButton)));
    await tester.pumpAndSettle();
    expect(productBuilds, 0);
    expect(find.text('Restore my account'), findsOneWidget);
  });
}
