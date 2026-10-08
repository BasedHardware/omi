import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/app_detail/reviews_list_page.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/show_app_options_sheet.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

App _app({String id = 'catalog-app', String? uid, List<AppReview> reviews = const [], bool enabled = false}) => App(
      id: id,
      uid: uid,
      name: 'Catalog $id',
      author: 'Omi',
      description: 'Sync your tasks with $id.',
      image: 'https://example.invalid/$id.png',
      capabilities: {'chat'},
      status: 'approved',
      category: 'productivity',
      approved: true,
      ratingCount: reviews.length,
      ratingAvg: 4.5,
      enabled: enabled,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    )..reviews = [...reviews];

AppReview _review(String uid, double score, {String response = ''}) => AppReview(
    uid: uid,
    ratedAt: DateTime.now().subtract(Duration(hours: score.round())),
    score: score,
    review: 'Review by $uid',
    username: uid,
    response: response);

/// Records the presentation owners' calls; mutations stay observable without HTTP.
class _RecordingAppProvider extends AppProvider {
  final publicChanges = <(String, bool)>[];
  final deletions = <String>[];
  final enables = <String>[];
  Completer<bool>? enableAnswer;

  @override
  Future<bool> toggleApp(String appId, bool isEnabled, int? idx) {
    enables.add(appId);
    return (enableAnswer = Completer<bool>()).future;
  }

  @override
  Future<void> toggleAppPublic(String appId, bool value) async => publicChanges.add((appId, value));

  @override
  Future deleteApp(String appId) async => deletions.add(appId);
}

class _Routes extends NavigatorObserver {
  final pushed = <Route<dynamic>>[];
  int pops = 0;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) => pushed.add(route);

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) => pops++;

  /// The page the last pushed route builds, without building it.
  Widget lastPage(WidgetTester tester) {
    final context = tester.element(find.byType(Navigator).first);
    return switch (pushed.last) {
      MaterialPageRoute(:final builder) || CupertinoPageRoute(:final builder) => builder(context),
      final route => throw TestFailure('Unexpected route $route'),
    };
  }
}

/// Answers each native 'present' with the next reply; an activity stays up until it is dismissed.
List<Map> _answerPresentations(List<Object? Function(Map snapshot)> replies, {List<String>? activities}) {
  final presented = <Map>[];
  final activity = <Completer<Map<String, Object?>>>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    switch (call.method) {
      case 'present':
        final snapshot = (call.arguments as Map)['snapshot'] as Map;
        presented.add(snapshot);
        final reply = replies[presented.length - 1](snapshot);
        if (reply is PlatformException) throw reply;
        return reply;
      case 'presentActivity':
        activities?.add((call.arguments as Map)['label'] as String);
        activity.add(Completer());
        return activity.last.future;
      case 'dismissPresentation':
        for (final pending in activity) {
          if (!pending.isCompleted) pending.complete({'reason': 'programmatic'});
        }
    }
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

Object? Function(Map) _send(String text) => (_) => {
      'action': 'send',
      'values': <String, Object?>{'review_reply_text': text},
      'reason': 'action'
    };
Object? Function(Map) _choose(String action) => (_) => {'action': action, 'values': <String, Object?>{}};
Object? _cancel(Map _) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'};

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<void> settle(WidgetTester tester) async {
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(seconds: 1));
    await NativeTestHost.settle(tester);
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last);

  NativeRow? row(WidgetTester tester, String id) {
    final current = surface(tester);
    return [...current.toolbar, ...current.sections.expand((section) => section.rows)]
        .where((row) => row.id == id)
        .singleOrNull;
  }

  Future<_Routes> pump(WidgetTester tester, Widget page, AppProvider provider) async {
    addTearDown(provider.dispose);
    final routes = _Routes();
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<AppProvider>.value(value: provider),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            navigatorObservers: [routes],
            // The app shell's Scaffold, which presents the existing SnackBar feedback.
            home: Scaffold(body: page))));
    await settle(tester);
    return routes;
  }

  testWidgets('without the native host every page keeps its complete Flutter presentation', (tester) async {
    SharedPreferencesUtil().uid = 'owner';
    await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [_review('a', 4)])), AppProvider());
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.text(_l10n.reply), findsOneWidget);
    final sent = <String>[];
    ReviewsListPage.debugReplySenderForTest = (_, reply, __) async {
      sent.add(reply);
      return true;
    };
    addTearDown(() => ReviewsListPage.debugReplySenderForTest = null);
    await tester.tap(find.text(_l10n.reply));
    await settle(tester);
    await tester.enterText(find.byType(TextField), '  Thanks  ');
    await tester.tap(find.text(_l10n.send));
    await settle(tester);
    expect(sent, ['Thanks']);
    expect(find.byType(OmiAlertDialog), findsNothing, reason: 'The dialog closes after sending');
    await pump(
        tester,
        CategoryAppsPage(
            category: Category(title: 'Productivity', id: 'productivity'),
            apps: const [],
            loadApps: (_) async => (apps: [_app()], pagination: <String, dynamic>{'total': 1}, category: null)),
        AppProvider());
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.text(_l10n.categoryAppCount(1)), findsOneWidget);
  });

  group('ReviewsListPage', () {
    late List<(String, String, String)> sent;
    setUp(() {
      sent = [];
      ReviewsListPage.debugReplySenderForTest = (appId, reply, reviewer) async {
        sent.add((appId, reply, reviewer));
        return true;
      };
      addTearDown(() => ReviewsListPage.debugReplySenderForTest = null);
    });

    testWidgets('offers star filters only for ratings that are present', (tester) async {
      NativeTestHost.install();
      final app = _app(reviews: [_review('a', 5), _review('b', 5), _review('c', 3)]);
      await pump(tester, ReviewsListPage(app: app), AppProvider());
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Every projected row is valid');
      final filter = row(tester, 'reviews_filter')!;
      expect(filter.options.keys, ['0', '3', '5']);
      expect(filter.options['5'], _l10n.starFilterLabel(5));
      expect(filter.value, '0');
      expect(row(tester, 'review:2'), isNotNull);

      await filter.action!('3');
      await settle(tester);
      expect(row(tester, 'reviews_filter')!.value, '3');
      expect(row(tester, 'review:0')!.title, 'c');
      expect(row(tester, 'review:1'), isNull);
    });

    testWidgets('an empty list says so and non-owners get no reply rows', (tester) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'visitor';
      await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [_review('a', 4)])), AppProvider());
      expect(row(tester, 'review:0'), isNotNull);
      expect(row(tester, 'review_reply:0'), isNull);

      await pump(tester, ReviewsListPage(key: const ValueKey('empty'), app: _app(uid: 'owner')), AppProvider());
      expect(row(tester, 'reviews_empty')!.title, _l10n.noReviewsFound);
    });

    testWidgets('an owner reply rejects blank text and sends the trimmed text once', (tester) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'owner';
      final review = _review('reviewer', 4);
      final provider = AppProvider();
      final activities = <String>[];
      final presented =
          _answerPresentations([_send('   '), _send('  Thanks for the review!  ')], activities: activities);
      await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [review])), provider);
      final reply = row(tester, 'review_reply:0')!;
      expect(reply.title, _l10n.reply);

      unawaited(reply.action!(null) as Future<void>?);
      await settle(tester);
      expect(presented, hasLength(2), reason: 'Blank text keeps the editor open');
      expect(presented.first['title'], _l10n.replyToReview);
      final text = (presented.first['sections'] as List).cast<Map>().single['rows'].single as Map;
      expect([text['kind'], text['title'], text['maximumLength']], ['text', _l10n.writeYourReply, 250]);
      expect(sent, [('catalog-app', 'Thanks for the review!', 'reviewer')]);
      expect(activities, [_l10n.replyToReview]);
      expect(review.response, 'Thanks for the review!');
      expect(row(tester, 'review_reply:0')!.title, _l10n.editReply);
      expect(find.text(_l10n.replySentSuccessfully), findsOneWidget);
    });

    testWidgets('a failed send keeps the editor open with the draft and mutates nothing', (tester) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'owner';
      ReviewsListPage.debugReplySenderForTest = (_, __, ___) async => throw Exception('offline');
      final review = _review('reviewer', 4);
      final presented = _answerPresentations([_send('Thanks'), _cancel]);
      await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [review])), AppProvider());

      unawaited(row(tester, 'review_reply:0')!.action!(null) as Future<void>?);
      await settle(tester);
      expect(presented, hasLength(2), reason: 'The editor reopens after the failure');
      final text = (presented.last['sections'] as List).cast<Map>().single['rows'].single as Map;
      expect(text['value'], 'Thanks');
      expect(review.response, isEmpty);
      expect(find.textContaining('offline'), findsOneWidget, reason: 'The existing failure toast');
    });

    testWidgets('a cancelled reply mutates nothing', (tester) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'owner';
      final review = _review('reviewer', 4, response: 'Earlier answer');
      final presented = _answerPresentations([_cancel]);
      await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [review])), AppProvider());
      expect(row(tester, 'review_reply:0')!.title, _l10n.editReply);

      unawaited(row(tester, 'review_reply:0')!.action!(null) as Future<void>?);
      await settle(tester);
      expect(presented, hasLength(1));
      expect(sent, isEmpty);
      expect(review.response, 'Earlier answer');
      expect(find.byType(OmiAlertDialog), findsNothing);
    });

    testWidgets('an unavailable native editor opens the Flutter reply dialog', (tester) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'owner';
      _answerPresentations([(_) => PlatformException(code: 'invalid_native_presentation')]);
      await pump(tester, ReviewsListPage(app: _app(uid: 'owner', reviews: [_review('reviewer', 4)])), AppProvider());

      unawaited(row(tester, 'review_reply:0')!.action!(null) as Future<void>?);
      await settle(tester);
      expect(find.byType(OmiAlertDialog), findsOneWidget);
      expect(sent, isEmpty);
    });
  });

  group('app options sheet', () {
    Future<(_Routes, _RecordingAppProvider)> pumpSheet(WidgetTester tester) async {
      NativeTestHost.install();
      final provider = _RecordingAppProvider();
      final routes = await pump(tester, const Scaffold(body: SizedBox()), provider);
      final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
      // The app's detail page, then the sheet over it.
      unawaited(navigator.push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: SizedBox()))));
      unawaited(navigator.push(MaterialPageRoute<void>(
          builder: (_) => ShowAppOptionsSheet(app: _app(uid: 'owner'), nativeTitle: 'Catalog catalog-app'))));
      await settle(tester);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Every projected row is valid');
      routes.pops = 0;
      return (routes, provider);
    }

    testWidgets('keep public changes visibility only after confirmation', (tester) async {
      final (routes, provider) = await pumpSheet(tester);
      final presented = _answerPresentations([_cancel, _choose('confirm')]);
      final toggle = row(tester, 'app_keep_public')!;
      expect([toggle.kind, toggle.value, toggle.title], ['toggle', false, _l10n.keepItemPublic(_l10n.itemApp)]);

      await toggle.action!(true);
      await settle(tester);
      expect(provider.publicChanges, isEmpty);
      expect(routes.pops, 0);

      await row(tester, 'app_keep_public')!.action!(true);
      await settle(tester);
      expect(presented.last['title'], _l10n.makeItemPublicQuestion(_l10n.itemApp));
      expect(provider.publicChanges, [('catalog-app', true)]);
      expect(routes.pops, 1, reason: 'The sheet closes after the change');
    });

    testWidgets('delete requires confirmation and closes the sheet and the app page', (tester) async {
      final (routes, provider) = await pumpSheet(tester);
      _answerPresentations([_cancel, _choose('confirm')]);
      final delete = row(tester, 'app_delete')!;
      expect(delete.destructive, isTrue);

      await delete.action!(null);
      await settle(tester);
      expect(provider.deletions, isEmpty);

      await row(tester, 'app_delete')!.action!(null);
      await settle(tester);
      expect(provider.deletions, ['catalog-app']);
      expect(routes.pops, 2);
    });

    testWidgets('manage closes the sheet and opens UpdateAppPage', (tester) async {
      final (routes, _) = await pumpSheet(tester);
      final manage = row(tester, 'app_manage')!;
      expect(manage.title, _l10n.manageApp);
      await manage.action!(null);
      expect(routes.pops, 1);
      expect(routes.lastPage(tester), isA<UpdateAppPage>());
    });
  });

  group('capability and category pages', () {
    testWidgets('capability apps load, fail with retry, empty and group rows open AppDetailPage', (tester) async {
      NativeTestHost.install();
      final provider = _RecordingAppProvider();
      final answers =
          <Completer<({List<Map<String, dynamic>> groups, Map<String, dynamic>? capability, int totalApps})>>[];
      final routes = await pump(
          tester,
          CapabilityAppsPage(
              capability: AppCapability(title: 'Chat', id: 'chat'),
              apps: const [],
              loadApps: (_) {
                answers.add(Completer());
                return answers.last.future;
              }),
          provider);
      expect(surface(tester).loading, isTrue);

      answers.last.completeError(Exception('offline'));
      await settle(tester);
      expect(surface(tester).failed, isTrue);
      expect(surface(tester).errorMessage, _l10n.unableToLoadApps);

      unawaited(surface(tester).onRefresh!(null) as Future<void>?);
      await settle(tester);
      expect(answers, hasLength(2), reason: 'Retry goes through the existing loader');
      answers.last.complete((groups: <Map<String, dynamic>>[], capability: null, totalApps: 0));
      await settle(tester);
      expect(surface(tester).failed, isFalse);
      expect(row(tester, 'capability_apps_empty')!.subtitle, _l10n.checkBackLaterForNewApps);

      unawaited(surface(tester).onRefresh!(null) as Future<void>?);
      await settle(tester);
      final apps = [_app(id: 'one'), _app(id: 'two', enabled: true)];
      answers.last.complete((
        groups: [
          {
            'category': {'id': 'productivity', 'title': 'Productivity'},
            'data': apps
          }
        ],
        capability: null,
        totalApps: 2
      ));
      await settle(tester);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Every projected row is valid');
      final section = surface(tester).sections.single;
      expect(section.footer, _l10n.categoryAppCount(2));
      expect(section.rows.map((row) => row.id), ['group_0_0', 'group_0_1']);
      expect(section.rows.first.kind, 'navigation');
      expect(section.rows.first.imageUri, 'https://example.invalid/one.png');
      expect(section.rows.first.subtitle, contains('Sync your tasks with one.'));
      expect(section.rows.first.options.keys, ['enable']);
      expect(section.rows.first.swipeTrailing, ['enable']);
      expect(section.rows.last.options, isEmpty, reason: 'An enabled app opens instead');

      unawaited(section.rows.first.action!('enable') as Future<void>?);
      await settle(tester);
      expect(provider.enables, ['one']);
      expect(row(tester, 'group_0_0')!.options, isEmpty, reason: 'No second enable while the owner answers');
      expect(row(tester, 'group_0_0')!.subtitle.split('\n').first, _l10n.pleaseWait,
          reason: 'The row shows the server call is running');
      provider.enableAnswer!.complete(true);
      await settle(tester);
      expect(row(tester, 'group_0_0')!.subtitle, isNot(contains(_l10n.pleaseWait)));
      expect(row(tester, 'group_0_0')!.options.keys, ['enable'], reason: 'The owner still reports it disabled');

      unawaited(section.rows.first.action!(null) as Future<void>?);
      expect(routes.lastPage(tester), isA<AppDetailPage>());
    });

    testWidgets('category apps show the count, empty and failed states, and rows open AppDetailPage', (tester) async {
      NativeTestHost.install();
      final provider = AppProvider();
      final answers =
          <Completer<({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? category})>>[];
      final routes = await pump(
          tester,
          CategoryAppsPage(
              category: Category(title: 'Productivity', id: 'productivity'),
              apps: const [],
              loadApps: (_) {
                answers.add(Completer());
                return answers.last.future;
              }),
          provider);
      expect(surface(tester).loading, isTrue);
      expect(surface(tester).sections, isEmpty);

      answers.last.completeError(Exception('offline'));
      await settle(tester);
      expect(surface(tester).failed, isTrue);

      unawaited(surface(tester).onRefresh!(null) as Future<void>?);
      await settle(tester);
      answers.last.complete((apps: <App>[], pagination: <String, dynamic>{'total': 0}, category: null));
      await settle(tester);
      expect(surface(tester).sections.single.title, _l10n.categoryAppCount(0));
      expect(row(tester, 'category_apps_empty')!.title, _l10n.noAppsInCategoryYet);

      unawaited(surface(tester).onRefresh!(null) as Future<void>?);
      await settle(tester);
      answers.last.complete((apps: [_app(id: 'one')], pagination: <String, dynamic>{'total': 7}, category: null));
      await settle(tester);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Every projected row is valid');
      expect(surface(tester).sections.single.title, _l10n.categoryAppCount(7));
      final app = row(tester, 'apps_0')!;
      expect(app.kind, 'navigation');
      expect(app.subtitle, isNot(contains(_l10n.pleaseWait)));

      provider
        ..apps = [_app(id: 'one')]
        ..appLoading = [true]
        ..notifyListeners();
      await settle(tester);
      expect(row(tester, 'apps_0')!.subtitle.split('\n').first, _l10n.pleaseWait,
          reason: "The owner's per-row loading flag shows as busy");
      provider
        ..appLoading = [false]
        ..notifyListeners();
      await settle(tester);

      unawaited(app.action!(null) as Future<void>?);
      expect(routes.lastPage(tester), isA<AppDetailPage>());
    });
  });
}
