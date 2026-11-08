import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/settings_plan_section.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/settings_plan_card_experiment.dart';

/// The Settings plan section is a plan card (name, Upgrade, this month's minutes) for Free and Plus,
/// and leaves the plain Plan & Usage row for every other plan.
class _Usage extends ChangeNotifier implements UsageProvider {
  _Usage(this.subscription, {this.showSubscriptionUI = true});

  @override
  final UserSubscriptionResponse? subscription;

  @override
  final bool showSubscriptionUI;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

UserSubscriptionResponse _response(PlanType plan, {int usedSeconds = 0, int limitSeconds = 0}) =>
    UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: usedSeconds,
      transcriptionSecondsLimit: limitSeconds,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

void _noop() {}

void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  const row = Text('Plan row', key: ValueKey('plan_row'));

  Future<void> pump(WidgetTester tester, UsageProvider usage,
      {SettingsPlanCardArm arm = SettingsPlanCardArm.card}) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('en'),
          home: Scaffold(body: SettingsPlanSection(row: row, planName: 'Free', onOpen: _noop, arm: arm)),
        ),
      ),
    );
  }

  testWidgets('Free is a plan card: name, minutes used and Upgrade, in place of the row', (tester) async {
    await pump(tester, _Usage(_response(PlanType.basic, usedSeconds: 240 * 60, limitSeconds: 300 * 60)));

    expect(find.byKey(const ValueKey('plan_row')), findsNothing);
    expect(find.byKey(const ValueKey('settings_row_planAndUsage')), findsOneWidget);
    expect(find.text('Free'), findsOneWidget);
    expect(find.text(en.minsUsedThisMonth('240', 300)), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(find.text(en.upgrade), findsOneWidget);
  });

  testWidgets('tapping the card outside Upgrade opens Plan & Usage', (tester) async {
    var opened = 0;
    await tester.pumpWidget(
      ChangeNotifierProvider<UsageProvider>.value(
        value: _Usage(_response(PlanType.basic, usedSeconds: 60, limitSeconds: 300 * 60)),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('en'),
          home: Scaffold(
            body: SettingsPlanSection(
              row: row,
              planName: 'Free',
              onOpen: () => opened++,
              arm: SettingsPlanCardArm.card,
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Free'));
    expect(opened, 1);
  });

  testWidgets('control keeps the row with minutes and a full-width Upgrade under it', (tester) async {
    await pump(
      tester,
      _Usage(_response(PlanType.basic, usedSeconds: 240 * 60, limitSeconds: 300 * 60)),
      arm: SettingsPlanCardArm.control,
    );

    expect(find.byKey(const ValueKey('plan_row')), findsOneWidget);
    expect(find.text('Free'), findsNothing);
    expect(find.text(en.minsUsedThisMonth('240', 300)), findsOneWidget);
    expect(find.byKey(const ValueKey('settings_plan_upgrade')), findsOneWidget);
  });

  group('experiment', () {
    tearDown(SettingsPlanCardExperiment.resetForTesting);

    test('an unknown or missing variant falls back to control and is not counted', () async {
      SettingsPlanCardExperiment.resetForTesting();
      expect(await SettingsPlanCardExperiment.resolve(readVariant: (_) async => null), SettingsPlanCardArm.control);
      expect(SettingsPlanCardExperiment.recordExposure(SettingsPlanCardArm.control), isFalse);
      expect(await SettingsPlanCardExperiment.resolve(readVariant: (_) async => 'other'), SettingsPlanCardArm.control);
      expect(await SettingsPlanCardExperiment.resolve(readVariant: (_) => Future.error('offline')),
          SettingsPlanCardArm.control);
    });

    test('an assigned arm is counted under the settings-plan-card flag', () async {
      expect(await SettingsPlanCardExperiment.resolve(readVariant: (_) async => 'card'), SettingsPlanCardArm.card);
      final recorded = <String>[];
      SettingsPlanCardExperiment.recordExposure(
        SettingsPlanCardArm.card,
        record: (key, variant) {
          recorded.add('$key=$variant');
          return true;
        },
      );
      expect(recorded, ['settings-plan-card=card']);
    });
  });

  testWidgets('Plus offers Upgrade to Unlimited', (tester) async {
    await pump(tester, _Usage(_response(PlanType.plus, usedSeconds: 60, limitSeconds: 1500 * 60)));

    expect(find.text(en.upgradeToUnlimited), findsOneWidget);
    expect(find.text(en.minsUsedThisMonth('1', 1500)), findsOneWidget);
  });

  testWidgets('Free with no transcription limit shows Upgrade without a meter', (tester) async {
    await pump(tester, _Usage(_response(PlanType.basic)));

    expect(find.byType(LinearProgressIndicator), findsNothing);
    expect(find.byKey(const ValueKey('settings_plan_upgrade')), findsOneWidget);
  });

  for (final plan in [PlanType.unlimitedV2, PlanType.unlimited, PlanType.operator, PlanType.architect]) {
    testWidgets('${plan.name} keeps the plain row', (tester) async {
      await pump(tester, _Usage(_response(plan)));

      expect(find.byKey(const ValueKey('plan_row')), findsOneWidget);
      expect(find.byKey(const ValueKey('settings_plan_upgrade')), findsNothing);
    });
  }

  testWidgets('hidden subscription UI keeps the plain row', (tester) async {
    await pump(tester, _Usage(_response(PlanType.basic, limitSeconds: 18000), showSubscriptionUI: false));

    expect(find.byKey(const ValueKey('settings_plan_upgrade')), findsNothing);
  });

  testWidgets('no subscription yet keeps the plain row', (tester) async {
    await pump(tester, _Usage(null));

    expect(find.byKey(const ValueKey('plan_row')), findsOneWidget);
    expect(find.byKey(const ValueKey('settings_plan_upgrade')), findsNothing);
  });
}
