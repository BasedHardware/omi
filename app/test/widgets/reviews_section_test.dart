import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/app_summary.dart';
import 'package:omi/pages/apps/app_detail/reviews_section.dart';

const _readerUid = 'reader-uid';

App _app({double? ratingAvg, int ratingCount = 0, AppReview? userReview}) => App(
      id: 'app-1',
      uid: 'author-uid',
      name: 'Notes Sync',
      author: 'Omi',
      description: 'Syncs notes',
      image: '',
      capabilities: {'chat'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingAvg: ratingAvg,
      ratingCount: ratingCount,
      userReview: userReview,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

/// The app detail page's wiring: the header reads the same [App] the reviews card edits, and the
/// card's callback rebuilds the page.
Widget _detailPage(App app, {required AppReviewSender send}) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) => ListView(
            children: [
              AppDetailSummary(
                name: app.name,
                author: app.author,
                official: false,
                ratingCount: app.ratingCount,
                rating: app.getRatingAvg(),
                installs: 0,
                action: const SizedBox.shrink(),
              ),
              RecentReviewsSection(
                reviews: app.reviews,
                app: app,
                userReview: app.userReview,
                sendReview: send,
                sendReviewUpdate: send,
                onReviewUpdated: () => setState(() {}),
              ),
            ],
          ),
        ),
      ),
    );

/// The five tappable stars of the review being written (the summary and review rows draw smaller ones).
Finder get _editableStars => find.byWidgetPredicate((widget) => widget is FaIcon && widget.size == 24);

Future<void> _submit(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('app_detail_submit_review_button')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().uid = _readerUid;
  });

  testWidgets('rating distribution renders its score, count, and five-star scale', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: RatingDistributionWidget(
            ratingAvg: 4.2,
            ratingCount: 7,
            reviews: [],
          ),
        ),
      ),
    );

    expect(find.text('4.2'), findsOneWidget);
    expect(find.text('7 ratings'), findsOneWidget);
    expect(find.byType(FaIcon), findsNWidgets(5));
  });

  testWidgets('the first review of an app shows its score as the rating, not null', (tester) async {
    final app = _app();
    final sent = <AppReview>[];
    await tester.pumpWidget(_detailPage(app, send: (appId, review) async {
      sent.add(review);
      return true;
    }));

    await tester.tap(_editableStars.at(3));
    await tester.pump();
    await _submit(tester);

    expect(sent.single.score, 4);
    expect(app.ratingCount, 1);
    expect(app.ratingAvg, 4);
    expect(find.text('4.0 (1)'), findsOneWidget);
    expect(find.textContaining('null'), findsNothing);
  });

  testWidgets('editing your review moves the average off your old score', (tester) async {
    final app = _app(
      ratingAvg: 4,
      ratingCount: 2,
      userReview: AppReview(uid: _readerUid, ratedAt: DateTime(2026, 10, 1), score: 5, review: 'Great'),
    );
    await tester.pumpWidget(_detailPage(app, send: (appId, review) async => true));
    expect(find.text('4.0 (2)'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.edit));
    await tester.pump();
    await tester.tap(_editableStars.first);
    await tester.pump();
    await _submit(tester);

    // (4.0 × 2 − 5 + 1) / 2: the edit replaces the reader's 5 with a 1 and adds no rating.
    expect(app.ratingCount, 2);
    expect(app.ratingAvg, 2);
    expect(find.text('2.0 (2)'), findsOneWidget);
  });

  testWidgets('a review the server rejects leaves the rating as it was', (tester) async {
    final app = _app(ratingAvg: 3, ratingCount: 4);
    await tester.pumpWidget(_detailPage(app, send: (appId, review) async => false));

    await tester.tap(_editableStars.last);
    await tester.pump();
    await _submit(tester);

    expect(app.ratingCount, 4);
    expect(app.ratingAvg, 3);
    expect(find.text('3.0 (4)'), findsOneWidget);
  });
}
