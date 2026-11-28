// Verifies legacy PlansSheet exposure against committed catalog render branches.
// Uses a fake catalog API with the storefront gate disabled; never opens checkout.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import '../support/recording_analytics.dart';

Map<String, dynamic> _price(String tier, String interval, {bool active = false}) => {
      'id': 'fixture_${tier}_$interval',
      'plan_id': tier,
      'title': 'Fixture plan',
      'interval': interval,
      'unit_amount': 3000,
      'currency': 'usd',
      'is_active': active,
    };

class _CatalogApi {
  final requests = <Completer<Map<String, dynamic>?>>[];
  Future<Map<String, dynamic>?> load() {
    final response = Completer<Map<String, dynamic>?>();
    requests.add(response);
    return response.future;
  }
}

/// Fake the catalog API boundary; run the actual production sheet and observers.
class _Usage extends UsageProvider {
  _Usage(this.api);
  final _CatalogApi api;
  Map<String, dynamic>? _catalog;
  bool _loading = false;
  @override
  Map<String, dynamic>? get availablePlans => _catalog;
  @override
  bool get isLoadingPlans => _loading;
  @override
  Future<void> loadAvailablePlans() async {
    _loading = true;
    notifyListeners();
    try {
      final response = await api.load();
      if (response != null) _catalog = response;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}

class _Host extends StatefulWidget {
  const _Host();
  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> with TickerProviderStateMixin {
  late final animation = AnimationController(vsync: this);
  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
        waveController: animation,
        notesController: animation,
        arrowController: animation,
        arrowAnimation: animation,
        readStorefrontGate: () async => false,
      );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late RecordingAnalytics recording;
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    recording = RecordingAnalytics();
    AnalyticsManager.configure(recording.adapter);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  Future<void> flush() => AnalyticsManager.flushPending(force: true);
  Iterable<Map<String, Object>> views() => recording.propertiesOf('Subscription Paywall Viewed');
  Finder upgrade() => find.byKey(const ValueKey('plans_sheet_upgrade_button'));

  Future<_Usage> mount(WidgetTester tester, _CatalogApi api, {PlanType? plan, bool cancelled = false}) async {
    tester.view.physicalSize = const Size(1000, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage(api);
    addTearDown(usage.dispose);
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
        plan: plan ?? PlanType.basic,
        // Keep the separate yearly-switch API row out of catalog-only fixtures.
        status: plan?.isPaid == true ? SubscriptionStatus.inactive : SubscriptionStatus.active,
        stripeSubscriptionId: plan?.isPaid == true ? 'fixture_subscription' : null,
        cancelAtPeriodEnd: cancelled,
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ));
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: _Host()),
      ),
    ));
    await tester.pump();
    await tester.pump();
    expect(api.requests, hasLength(1));
    return usage;
  }

  Future<void> respond(WidgetTester tester, _CatalogApi api, List<Map<String, dynamic>>? plans) async {
    api.requests.last.complete(plans == null
        ? null
        : {
            'plans': <dynamic>[...plans]
          });
    await tester.pump();
    await tester.pump();
    await flush();
    expect(tester.takeException(), isNull);
  }

  testWidgets('legacy loading waits for options and refresh does not reset the mount latch', (tester) async {
    final api = _CatalogApi();
    final usage = await mount(tester, api);
    await flush();
    expect(find.byType(PlanOptionShimmer), findsNWidgets(2));
    expect(upgrade(), findsNothing);
    expect(views(), isEmpty);
    await respond(tester, api, [_price('unlimited_v2', 'year'), _price('unlimited_v2', 'month')]);
    expect(find.byType(PlanOptionCard), findsNWidgets(2));
    expect(upgrade(), findsOneWidget);
    expect(views(), hasLength(1));
    final refresh = usage.loadAvailablePlans();
    await tester.pump();
    await flush();
    expect(find.byType(PlanOptionShimmer), findsNWidgets(2));
    expect(upgrade(), findsNothing);
    expect(views(), hasLength(1));
    await respond(tester, api, [_price('unlimited_v2', 'year')]);
    await refresh;
    expect(find.byType(PlanOptionCard), findsNWidgets(2), reason: 'single-tier fallback is preserved');
    expect(views(), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('legacy failed and empty catalogs never consume the eventual valid view', (tester) async {
    final api = _CatalogApi();
    final usage = await mount(tester, api);
    await respond(tester, api, null);
    expect(find.byType(PlanOptionCard), findsNothing);
    expect(upgrade(), findsNothing);
    expect(views(), isEmpty);
    final empty = usage.loadAvailablePlans();
    await respond(tester, api, []);
    await empty;
    expect(find.byType(PlanOptionCard), findsNothing);
    expect(upgrade(), findsNothing);
    expect(views(), isEmpty);
    final valid = usage.loadAvailablePlans();
    await respond(tester, api, [_price('unlimited_v2', 'year')]);
    await valid;
    expect(upgrade(), findsOneWidget);
    expect(views(), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('multi-tier catalog without chosen-interval cards waits for the actual option branch', (tester) async {
    final api = _CatalogApi();
    final usage = await mount(tester, api);
    await respond(tester, api, [_price('plus', 'month'), _price('unlimited_v2', 'month')]);
    expect(find.byType(PlanOptionCard), findsNothing);
    expect(upgrade(), findsNothing);
    expect(views(), isEmpty);
    final valid = usage.loadAvailablePlans();
    await respond(tester, api, [_price('plus', 'year'), _price('unlimited_v2', 'year')]);
    await valid;
    expect(find.byType(PlanOptionCard), findsNWidgets(2));
    expect(upgrade(), findsOneWidget);
    expect(views(), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('legacy cards without a selected checkout price hide Upgrade until a valid interval is selected',
      (tester) async {
    final api = _CatalogApi();
    await mount(tester, api);
    await respond(tester, api, [_price('unlimited_v2', 'month')]);
    expect(find.byType(PlanOptionCard), findsNWidgets(2), reason: 'Existing single-tier card fallback remains');
    expect(upgrade(), findsNothing, reason: 'The default yearly interval has no checkout price');
    await tester.ensureVisible(find.byType(PlanOptionCard).last);
    await tester.tap(find.byType(PlanOptionCard).last);
    await tester.pump();
    expect(upgrade(), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('paid multi-tier cards normalize selection before rendering Continue in the same build', (tester) async {
    final api = _CatalogApi();
    await mount(tester, api, plan: PlanType.plus);
    await respond(tester, api, [
      _price('plus', 'month', active: true),
      _price('plus', 'year'),
      _price('unlimited_v2', 'year'),
    ]);
    expect(find.byType(PlanOptionCard), findsNWidgets(2));
    expect(upgrade(), findsOneWidget);
    expect(tester.widget<PlanOptionCard>(find.byType(PlanOptionCard).last).isSelected, isTrue);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('unknown current plan follows actual legacy cards and uses the closed unknown label', (tester) async {
    final api = _CatalogApi();
    await mount(tester, api, plan: PlanType.unknown('future_fixture_plan'));
    await flush();
    expect(views(), isEmpty);
    await respond(tester, api, [_price('unlimited_v2', 'year')]);
    expect(find.byType(PlanOptionCard), findsNWidgets(2));
    expect(upgrade(), findsOneWidget);
    expect(views(), hasLength(1));
    expect(views().single, containsPair('current_plan', 'unknown'));
    await tester.pumpWidget(const SizedBox());
  });

  for (final state in ['annual', 'scheduled', 'cancelled']) {
    testWidgets('legacy $state status counts only if purchase cards are actually rendered', (tester) async {
      final api = _CatalogApi();
      await mount(tester, api, plan: PlanType.unlimitedV2, cancelled: state == 'cancelled');
      await respond(tester, api, [
        _price('unlimited_v2', 'year', active: true),
        _price('unlimited_v2', 'month', active: state == 'scheduled'),
      ]);
      expect(find.byType(PlanOptionCard), state == 'cancelled' ? findsNWidgets(2) : findsNothing);
      expect(views(), state == 'cancelled' ? hasLength(1) : isEmpty);
      expect(upgrade(), findsNothing, reason: 'Annual, scheduled and cancellation constraints are retained');
      await tester.pumpWidget(const SizedBox());
    });
  }
}
