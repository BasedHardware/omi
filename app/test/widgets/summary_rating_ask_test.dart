import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/widgets/app_review_prompt.dart';

const _askDelay = AppReviewPrompt.defaultRatingAskDelay;

// Any conversation summary asks "Are you enjoying Omi?" right after it opens, once per user. Yes opens the
// store sheet; No ends rating requests for that user. The flag off restores the native-only path.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences storage;

  Future<void> setUpPrefs({String answer = ''}) async {
    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      'uid': 'user-1',
      'onboardingCompleted': true,
      if (answer.isNotEmpty) 'ratingAskAnswer': answer,
      'app_review_policy_v1': jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': DateTime(2026, 9, 1).millisecondsSinceEpoch,
        'readingDays': ['2026-09-01'],
        'attempts': <Object>[],
      }),
    });
    storage = await SharedPreferences.getInstance();
    await SharedPreferencesUtil.init();
    AppReviewPrompt.resetSessionForTesting();
  }

  AppReviewService service(void Function() onNative) => AppReviewService.forTesting(
        storage: storage,
        clock: () => DateTime(2026, 10, 9, 12),
        platform: 'ios',
        appVersion: '1.0.560',
        isAvailable: () async => true,
        requestNativeReview: () async => onNative(),
      );

  Future<void> pumpSummary(
    WidgetTester tester, {
    required AppReviewService reviewService,
    void Function()? onStoreReview,
    String contentId = 'conversation-1',
    bool enabled = true,
    bool flagOn = true,
  }) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: AppReviewPrompt(
          key: ValueKey(contentId),
          contentId: contentId,
          moment: AppReviewMoment.conversationRead,
          enabled: enabled,
          service: reviewService,
          isRatingAskEnabled: () async => flagOn,
          requestStoreReview: () async => onStoreReview?.call(),
          child: const SingleChildScrollView(child: SizedBox(height: 120, child: Text('Summary'))),
        ),
      ),
    ));
    await tester.pump();
  }

  Future<void> readLong(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
  }

  testWidgets('an existing user is asked right after a summary opens; Yes opens the store sheet and is final',
      (tester) async {
    await setUpPrefs();
    var store = 0, native = 0;
    await pumpSummary(tester, reviewService: service(() => native++), onStoreReview: () => store++);

    await tester.pump(_askDelay - const Duration(milliseconds: 500));
    expect(find.text('Are you enjoying Omi?'), findsNothing, reason: 'not mid page transition');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.text('Are you enjoying Omi?'), findsOneWidget);

    await tester.tap(find.text('Yes'));
    await tester.pumpAndSettle();
    expect(store, 1);
    expect(native, 0, reason: 'no native request in the session the ask was shown');
    expect(SharedPreferencesUtil().ratingAskAnswer, 'yes');

    // A new session: no second ask; the native reading prompt may run for a Yes user.
    AppReviewPrompt.resetSessionForTesting();
    await pumpSummary(tester, reviewService: service(() => native++), contentId: 'conversation-2');
    await readLong(tester);
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(native, 1);
  });

  testWidgets('No is final and stops every later rating request', (tester) async {
    await setUpPrefs();
    var store = 0, native = 0;
    await pumpSummary(tester, reviewService: service(() => native++), onStoreReview: () => store++);
    await readLong(tester);
    await tester.tap(find.text('No'));
    await tester.pumpAndSettle();
    expect(store, 0);
    expect(SharedPreferencesUtil().ratingAskAnswer, 'no');

    AppReviewPrompt.resetSessionForTesting();
    await pumpSummary(tester, reviewService: service(() => native++), contentId: 'conversation-2');
    await readLong(tester);
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(native, 0);
  });

  testWidgets('an answer given in onboarding counts: no ask on summaries', (tester) async {
    await setUpPrefs(answer: 'no');
    var native = 0;
    await pumpSummary(tester, reviewService: service(() => native++));
    await readLong(tester);
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(native, 0);
  });

  testWidgets('leaving the summary before the delay asks nothing and keeps the user unasked', (tester) async {
    await setUpPrefs();
    await pumpSummary(tester, reviewService: service(() {}));
    await tester.pump(const Duration(milliseconds: 300));
    await pumpSummary(tester, reviewService: service(() {}), enabled: false);
    await readLong(tester);
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(SharedPreferencesUtil().ratingAskAnswer, isEmpty);
  });

  testWidgets('flag off: no ask, and the native reading prompt works as before', (tester) async {
    await setUpPrefs();
    var native = 0;
    await pumpSummary(tester, reviewService: service(() => native++), flagOn: false);
    await readLong(tester);
    expect(find.text('Are you enjoying Omi?'), findsNothing);
    expect(native, 1);
    expect(SharedPreferencesUtil().ratingAskAnswer, isEmpty);
  });
}
