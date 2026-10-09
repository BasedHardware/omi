import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/widgets/app_review_prompt.dart';

const _askDelay = AppReviewPrompt.defaultFirstSummaryAskDelay;

// The first conversation summary a user opens after onboarding asks "Are you enjoying Omi?"
// about seven seconds in. Yes opens the store review sheet; No closes. It asks once.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences storage;

  Future<void> setUpPrefs({required bool pending}) async {
    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      'uid': 'user-1',
      'onboardingCompleted': true,
      if (pending) 'firstSummaryRatingPending': true,
      'app_review_policy_v1': jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': DateTime(2026, 10, 1).millisecondsSinceEpoch,
        'readingDays': ['2026-10-01'],
        'attempts': <Object>[],
      }),
    });
    storage = await SharedPreferences.getInstance();
    await SharedPreferencesUtil.init();
    AppReviewPrompt.resetSessionForTesting();
  }

  AppReviewService service({required void Function() onNative}) => AppReviewService.forTesting(
        storage: storage,
        clock: () => DateTime(2026, 10, 8, 12),
        platform: 'ios',
        appVersion: '1.0.559',
        isAvailable: () async => true,
        requestNativeReview: () async => onNative(),
      );

  Future<void> pumpSummary(
    WidgetTester tester, {
    required AppReviewService reviewService,
    required void Function() onStoreReview,
    bool enabled = true,
    bool flagOn = true,
  }) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: AppReviewPrompt(
          contentId: 'conversation-1',
          moment: AppReviewMoment.conversationRead,
          enabled: enabled,
          service: reviewService,
          isRatingAskEnabled: () async => flagOn,
          requestStoreReview: () async => onStoreReview(),
          child: const SingleChildScrollView(child: SizedBox(height: 120, child: Text('Summary'))),
        ),
      ),
    ));
    await tester.pump();
  }

  testWidgets('first summary after onboarding asks after ~7s; Yes opens the store sheet once', (tester) async {
    await setUpPrefs(pending: true);
    var store = 0, native = 0;
    await pumpSummary(tester, reviewService: service(onNative: () => native++), onStoreReview: () => store++);

    await tester.pump(_askDelay - const Duration(seconds: 1));
    expect(find.text('Are you enjoying Omi?'), findsNothing, reason: 'not before the delay');

    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsOneWidget);
    expect(find.text('Yes'), findsOneWidget);
    expect(find.text('No'), findsOneWidget);

    await tester.tap(find.text('Yes'));
    await tester.pumpAndSettle();
    expect(store, 1);
    expect(native, 0, reason: 'the reading-moment prompt stays quiet in the same session');
    expect(SharedPreferencesUtil().firstSummaryRatingPending, isFalse);

    // Reopening a summary later in the session never asks again.
    await tester.pumpWidget(const SizedBox());
    await pumpSummary(tester, reviewService: service(onNative: () => native++), onStoreReview: () => store++);
    await tester.pump(_askDelay * 2);
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(store, 1);
  });

  testWidgets('No closes the ask without opening the store sheet', (tester) async {
    await setUpPrefs(pending: true);
    var store = 0;
    await pumpSummary(tester, reviewService: service(onNative: () {}), onStoreReview: () => store++);
    await tester.pump(_askDelay);
    await tester.pumpAndSettle();
    await tester.tap(find.text('No'));
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(store, 0);
    expect(SharedPreferencesUtil().firstSummaryRatingPending, isFalse);
  });

  testWidgets('existing users who did not just onboard are never asked', (tester) async {
    await setUpPrefs(pending: false);
    var store = 0;
    await pumpSummary(tester, reviewService: service(onNative: () {}), onStoreReview: () => store++);
    await tester.pump(_askDelay * 2);
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(store, 0);
  });

  testWidgets('leaving the summary before the delay cancels the ask and keeps it pending', (tester) async {
    await setUpPrefs(pending: true);
    await pumpSummary(tester, reviewService: service(onNative: () {}), onStoreReview: () {});
    await tester.pump(const Duration(seconds: 3));
    await pumpSummary(tester, reviewService: service(onNative: () {}), onStoreReview: () {}, enabled: false);
    await tester.pump(_askDelay * 2);
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(SharedPreferencesUtil().firstSummaryRatingPending, isTrue);
  });

  testWidgets('flag off keeps the ask pending and shows nothing', (tester) async {
    await setUpPrefs(pending: true);
    await pumpSummary(tester, reviewService: service(onNative: () {}), onStoreReview: () {}, flagOn: false);
    await tester.pump(_askDelay);
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(SharedPreferencesUtil().firstSummaryRatingPending, isTrue);
  });
}
