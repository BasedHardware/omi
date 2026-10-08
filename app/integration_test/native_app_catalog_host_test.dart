import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/pages/apps/app_detail/reviews_section.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/show_app_options_sheet.dart';

import 'journeys/support/fixture_backend.dart';
import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/fakes.dart';

/// Native app catalog and reviews on Simulator, with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
final _l10n = lookupAppLocalizations(const Locale('en'));
const _config = MethodChannel('com.omi.native_ui/config');

App _ownedApp() => App(
      id: 'native-catalog-fixture',
      uid: JourneyFixtureBackend.fixtureUid,
      name: 'Fixture app',
      author: 'Fixture',
      description: 'A seeded app for UI verification',
      image: 'https://example.com/logo.png',
      capabilities: {'chat'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: 2,
      ratingAvg: 4.5,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    )..reviews = [
        AppReview(
            uid: 'reviewer-one',
            ratedAt: DateTime(2026, 10, 1),
            score: 5,
            review: 'Exactly what I needed',
            username: 'Reviewer One'),
        AppReview(uid: 'reviewer-two', ratedAt: DateTime(2026, 9, 20), score: 4, review: 'Good', username: 'Two'),
      ];

/// Answers the reply editor with [reply] and keeps activities and toasts inert, standing in for the
/// person; the reply itself goes through the existing HTTP owner to the fixture backend.
void _answerReplyEditor(String reply) {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final activities = <Completer<Object?>>[];
  messenger.setMockMethodCallHandler(_config, (call) async {
    switch (call.method) {
      case 'isSupported':
        return true;
      case 'present':
        return {
          'action': 'send',
          'values': {'review_reply_text': reply},
          'reason': 'action'
        };
      case 'presentActivity':
        activities.add(Completer());
        return activities.last.future;
      case 'dismissPresentation':
        for (final activity in activities) {
          if (!activity.isCompleted) activity.complete({'reason': 'programmatic'});
        }
      case 'toast':
        return 'timeout';
    }
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
}

Future<void> _settle(WidgetTester tester) async {
  for (var step = 0; step < 6; step++) {
    await tester.pump(const Duration(milliseconds: 500));
  }
}

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('native app detail opens the native reviews sheet, the full list and an owner reply', (tester) async {
      final backend = await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      const replyPath = '/v1/apps/native-catalog-fixture/review/reply';
      // The fixture backend accepts the reply, so the existing HTTP owner sends it for real.
      backend.failNext('PATCH', replyPath, status: 200);
      final app = _ownedApp();
      await primeNetworkImages(tester, [app.image]);
      await tester.pumpWidget(nativeHostApp(AppDetailPage(app: app), providers: [
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]));
      await checkNativeHost(tester, 'native-app-catalog-reviews-app-detail-dark');

      unawaited(Future.sync(() => nativeProjectedRow(tester, 'app_reviews').action!(null)));
      await _settle(tester);
      expect(find.byType(RecentReviewsSection), findsOneWidget, reason: 'The native sheet hosts the section');
      expect(nativeProjectedRow(tester, 'app_reviews_all').title, _l10n.ratingsAndReviews);

      unawaited(Future.sync(() => nativeProjectedRow(tester, 'app_reviews_all').action!(null)));
      await _settle(tester);
      expect(find.byType(ReviewsListPage), findsOneWidget);
      await checkNativeHost(tester, 'native-app-catalog-reviews-list-dark');
      expect(nativeProjectedRow(tester, 'reviews_filter').options.keys, ['0', '4', '5']);
      expect(nativeProjectedRow(tester, 'review_reply:0').title, _l10n.reply);

      _answerReplyEditor('  Thank you!  ');
      unawaited(Future.sync(() => nativeProjectedRow(tester, 'review_reply:0').action!(null)));
      await _settle(tester);
      expect(backend.countOf('PATCH', replyPath), 1);
      expect(app.reviews.first.response, 'Thank you!');
      expect(nativeProjectedRow(tester, 'review_reply:0').title, _l10n.editReply);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native reviews sheet and app options sheet', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final app = _ownedApp();
      await tester.pumpWidget(nativeHostApp(
          Scaffold(body: RecentReviewsSection(nativePage: true, app: app, reviews: app.reviews.take(3).toList()))));
      await checkNativeHost(tester, 'native-app-catalog-reviews-sheet-dark');
      expect(nativeProjectedRow(tester, 'app_reviews_all').kind, 'navigation');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();

      await tester.pumpWidget(nativeHostApp(Scaffold(body: ShowAppOptionsSheet(app: app, nativeTitle: app.name))));
      await checkNativeHost(tester, 'native-app-catalog-reviews-app-options-dark');
      expect(nativeProjectedRow(tester, 'app_keep_public').kind, 'toggle');
      expect(nativeProjectedRow(tester, 'app_manage').title, _l10n.manageApp);
      expect(nativeProjectedRow(tester, 'app_delete').destructive, isTrue);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native capability and category app lists', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final app = _ownedApp();
      await primeNetworkImages(tester, [app.image]);
      await tester.pumpWidget(nativeHostApp(CapabilityAppsPage(
          capability: AppCapability(title: 'Chat', id: 'chat'),
          apps: const [],
          loadApps: (_) async => (
                groups: [
                  {
                    'category': {'id': 'productivity', 'title': 'Productivity'},
                    'data': [app]
                  }
                ],
                capability: null,
                totalApps: 1
              ))));
      await checkNativeHost(tester, 'native-app-catalog-reviews-capability-dark');
      expect(nativeProjectedRow(tester, 'group_0_0').kind, 'navigation');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();

      await tester.pumpWidget(nativeHostApp(CategoryAppsPage(
          category: Category(title: 'Productivity', id: 'productivity'),
          apps: const [],
          loadApps: (_) async => (apps: [app], pagination: <String, dynamic>{'total': 1}, category: null))));
      await checkNativeHost(tester, 'native-app-catalog-reviews-category-dark');
      expect(nativeProjectedRow(tester, 'apps_0').kind, 'navigation');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  });
}
