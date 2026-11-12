import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/pages/settings/widgets/yearly_retention_placement.dart';
import 'package:omi/pages/settings/widgets/yearly_switch.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../support/recording_analytics.dart';

const output = String.fromEnvironment('YEARLY_RETENTION_RENDER_OUTPUT');
final captureKey = GlobalKey();
final offer = wire.GeneratedYearlySwitchResponse(
    eligible: true,
    reason: 'eligible',
    planId: 'unlimited_v2',
    priceId: 'synthetic_yearly',
    currency: 'usd',
    monthlyAmount: 2999,
    yearlyAmount: 26991,
    savingsAmount: 8997,
    amountDueToday: 24492,
    renewsAt: DateTime.utc(2027, 11, 12).millisecondsSinceEpoch ~/ 1000,
    prorationDate: DateTime.utc(2026, 11, 12).millisecondsSinceEpoch ~/ 1000);

class Usage extends UsageProvider {
  int cancellations = 0;
  @override
  Future<void> fetchSubscription() async {}
  @override
  Future<void> loadAvailablePlans() async {}
  @override
  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async {
    cancellations++;
    return false;
  }
}

Future<Usage> pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(430, 932);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final usage = Usage();
  usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
          plan: PlanType.unlimitedV2,
          status: SubscriptionStatus.active,
          stripeSubscriptionId: 'synthetic_monthly',
          currentPriceId: 'synthetic_month',
          currentPeriodEnd: DateTime.utc(2026, 12, 12).millisecondsSinceEpoch ~/ 1000),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0));
  await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: RepaintBoundary(
          key: captureKey,
          child: MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: buildOmiTheme(brightness: Brightness.light),
              locale: const Locale('en'),
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: child))));
  await tester.pumpAndSettle();
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox.shrink());
    usage.dispose();
  });
  return usage;
}

Future<void> confirmStep(WidgetTester tester) async {
  final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold).first));
  await tester.tap(find.text(l10n.cancelReasonTooExpensive));
  await tester.pumpAndSettle();
  await tester.tap(find.text(l10n.continueButton));
  await tester.pumpAndSettle();
  await tester.tap(find.text(l10n.continueButton));
  await tester.pumpAndSettle();
}

Future<void> screenshot(WidgetTester tester, String name) async {
  if (output.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = captureKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(output).create(recursive: true);
    await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Future<void> fonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final entry in manifest) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'FlutterTest'
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
}

void iosTestWidgets(String description, WidgetTesterCallback callback) =>
    testWidgets(description, callback, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

void main() {
  late RecordingAnalytics analytics;
  setUp(() async {
    OmiColors.active = OmiPalette.light;
    SharedPreferences.setMockInitialValues({'uid': 'synthetic-uid'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    analytics = RecordingAnalytics();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
  });
  tearDown(() {
    AnalyticsManager.resetForTesting();
  });

  for (final treatment in [false, true]) {
    iosTestWidgets('cancel ${treatment ? 'treatment' : 'control'} renders and Cancel stays reachable', (tester) async {
      if (output.isNotEmpty) await tester.runAsync(fonts);
      final usage = await pump(
          tester,
          CancelSubscriptionFlow(
              loadOffer: () async => const wire.GeneratedRetentionOfferResponse(
                  eligible: true,
                  percentOff: 50,
                  durationMonths: 3,
                  regularAmount: 2999,
                  discountedAmount: 1500,
                  currency: 'usd'),
              yearlyClaim: (_) async => treatment ? offer : null,
              yearlyEnabled: () async => true,
              yearlyPreview: ({bool preview = false}) async => offer,
              yearlyApply: ({required priceId, required prorationDate, required expectedAmountDue}) async =>
                  {'error': true, 'status_code': 402}));
      await confirmStep(tester);
      final key = find.byKey(const ValueKey('yearly_retention_cancel'));
      expect(key, treatment ? findsOneWidget : findsNothing);
      final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold).first));
      expect(find.text(l10n.cancelSubscription).hitTestable(), findsOneWidget);
      analytics.expectSingle('Retention Offer Shown', {'reason': 'too_expensive', 'percent_off': 50});
      await screenshot(tester, treatment ? '003-mobile-ios-cancel-after' : '002-mobile-ios-cancel-control');
      if (treatment) {
        await tester.tap(key);
        await tester.pumpAndSettle();
        expect(find.text('US\$244.92'), findsOneWidget);
        await screenshot(tester, '006-mobile-ios-price-preview');
        await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
        await tester.pumpAndSettle();
        expect(find.text(l10n.yearlySwitchDeclined), findsOneWidget);
        await screenshot(tester, '007-mobile-ios-payment-declined');
        await tester.tap(find.byKey(const Key('yearly_switch_cancel')));
        await tester.pumpAndSettle();
        expect(find.text(l10n.cancelSubscription).hitTestable(), findsOneWidget);
      }
      await tester.tap(find.text(l10n.cancelSubscription));
      await tester.pumpAndSettle();
      expect(usage.cancellations, 1);
      expect(tester.takeException(), isNull);
    });
  }

  iosTestWidgets('pending admission never blocks cancellation', (tester) async {
    final pending = Completer<wire.GeneratedYearlySwitchResponse?>();
    final usage = await pump(
        tester,
        CancelSubscriptionFlow(
            loadOffer: () async => null, yearlyClaim: (_) => pending.future, yearlyEnabled: () async => true));
    await confirmStep(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold).first));
    await tester.tap(find.text(l10n.cancelSubscription));
    await tester.pumpAndSettle();
    expect(usage.cancellations, 1);
    pending.complete(null);
    await tester.pumpAndSettle();
  });

  iosTestWidgets('engaged placement renders once through rebuilds; flag off hides it', (tester) async {
    if (output.isNotEmpty) await tester.runAsync(fonts);
    var enabled = true;
    var claims = 0;
    final usage = await pump(
        tester,
        Scaffold(
            appBar: AppBar(title: Text('Home', style: OmiType.headline.copyWith(fontFamily: 'Roboto'))),
            body: ListView(children: [
              YearlyRetentionPlacement(
                  surface: YearlySwitchSurface.engaged,
                  claim: (_) async {
                    claims++;
                    return offer;
                  },
                  readEnabled: () async => enabled)
            ])));
    expect(claims, 1);
    await screenshot(tester, '005-mobile-ios-engaged-after');
    usage.notifyListeners();
    await tester.pumpAndSettle();
    expect(claims, 1);
    analytics.expectSingle('Yearly Retention Observation',
        {'placement': 'engaged', 'action': 'shown', 'variant': 'treatment', 'experiment_version': 1});
    enabled = false;
    await tester.pump(const Duration(seconds: 30));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('yearly_retention_engaged')), findsNothing);
    await screenshot(tester, '004-mobile-ios-engaged-before');
    enabled = true;
    usage.notifyListeners();
    await tester.pumpAndSettle();
    expect(claims, 1);
  });

  iosTestWidgets('flag disabled between preview and confirm prevents payment', (tester) async {
    var enabled = true;
    var charges = 0;
    await pump(
        tester,
        Scaffold(
            body: YearlyRetentionPlacement(
                surface: YearlySwitchSurface.engaged,
                claim: (_) async => offer,
                readEnabled: () async => enabled,
                loadPreview: ({bool preview = false}) async => offer,
                apply: ({required priceId, required prorationDate, required expectedAmountDue}) async {
                  charges++;
                  return {'status': 'success'};
                })));
    await tester.tap(find.byKey(const ValueKey('yearly_retention_engaged')));
    await tester.pumpAndSettle();
    enabled = false;
    await tester.tap(find.byKey(const Key('yearly_switch_confirm')));
    await tester.pumpAndSettle();
    expect(charges, 0);
    expect(find.byKey(const Key('yearly_switch_confirm')), findsNothing);
  });
}
