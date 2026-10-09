import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));

App _app(AppReview review) => App(
      id: 'reviewed-app',
      uid: 'owner',
      name: 'Reviewed app',
      author: 'Omi',
      description: 'An app with one review.',
      image: 'https://example.invalid/app.png',
      capabilities: {'chat'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: 1,
      ratingAvg: 4,
      enabled: false,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    )..reviews = [review];

/// Records local reply updates so a failed send is observably not applied.
class _RecordingAppProvider extends AppProvider {
  final localReplies = <(String, String, String)>[];

  @override
  void updateLocalAppReviewResponse(String appId, String response, String reviewId) =>
      localReplies.add((appId, response, reviewId));
}

void main() {
  late AppReview review;
  late _RecordingAppProvider provider;
  late List<String> sent;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    SharedPreferencesUtil().uid = 'owner';
    review = AppReview(
      uid: 'reviewer',
      ratedAt: DateTime.now(),
      score: 4,
      review: 'Nice app',
      username: 'reviewer',
      response: '',
    );
    provider = _RecordingAppProvider();
    sent = [];
  });

  tearDown(() => ReviewsListPage.debugReplySenderForTest = null);

  /// The page has continuously animating content, so it never settles; let transitions finish.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
  }

  Future<void> sendReply(WidgetTester tester, {required bool answer}) async {
    ReviewsListPage.debugReplySenderForTest = (_, reply, __) async {
      sent.add(reply);
      return answer;
    };
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(
            create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {}),
          ),
          ChangeNotifierProvider<AppProvider>.value(value: provider),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(body: ReviewsListPage(app: _app(review))),
        ),
      ),
    );
    await settle(tester);
    await tester.tap(find.text(_l10n.reply));
    await settle(tester);
    await tester.enterText(find.byType(TextField), '  Thanks!  ');
    await tester.tap(find.text(_l10n.send));
    await settle(tester);
  }

  testWidgets('a sent reply closes the dialog, updates the review and confirms', (tester) async {
    await sendReply(tester, answer: true);

    expect(sent, ['Thanks!']);
    expect(find.byType(OmiAlertDialog), findsNothing);
    expect(find.text(_l10n.replySentSuccessfully), findsOneWidget);
    expect(provider.localReplies, [('reviewed-app', 'Thanks!', 'reviewer')]);
    expect(review.response, 'Thanks!');
  });

  testWidgets('a refused reply keeps the text, shows the error and leaves the review unreplied', (tester) async {
    await sendReply(tester, answer: false);

    expect(sent, ['Thanks!']);
    expect(find.text(_l10n.replySentSuccessfully), findsNothing);
    expect(find.text(_l10n.failedToSendReply(_l10n.somethingWentWrongTryAgain)), findsOneWidget);
    expect(find.byType(OmiAlertDialog), findsOneWidget, reason: 'The dialog stays open for a retry');
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, '  Thanks!  ');
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue, reason: 'Sending is re-enabled');
    expect(provider.localReplies, isEmpty);
    expect(review.response, isEmpty);
    expect(review.respondedAt, isNull);
  });
}
