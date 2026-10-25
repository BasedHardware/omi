import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/omi_theme.dart';

class _Harness extends StatefulWidget {
  const _Harness();

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> with TickerProviderStateMixin {
  late final AnimationController _wave = AnimationController(vsync: this);
  late final AnimationController _notes = AnimationController(vsync: this);
  late final AnimationController _arrow = AnimationController(vsync: this);

  @override
  void dispose() {
    _wave.dispose();
    _notes.dispose();
    _arrow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _wave,
      notesController: _notes,
      arrowController: _arrow,
      arrowAnimation: _arrow,
      readStorefrontGate: () async => false,
    );
  }
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  PlatformManager.initializeForLocalHarness();
  await SharedPreferencesUtil.init();
  final usage = UsageProvider();
  usage.debugSetSubscription(
    UserSubscriptionResponse(
      subscription: Subscription(
        plan: PlanType.plus,
        status: SubscriptionStatus.active,
        stripeSubscriptionId: 'sub_fixture',
      ),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ),
  );
  usage.debugSetAvailablePlans(
    GeneratedAvailablePlansResponse.fromJson({
      'plans': [
        for (final plan in ['plus', 'unlimited_v2'])
          for (final interval in ['month', 'year'])
            {
              'id': 'price_${plan}_$interval',
              'plan_id': plan,
              'title': plan == 'plus' ? 'Plus' : 'Unlimited',
              'interval': interval,
              'unit_amount': (plan == 'plus' ? 1800 : 4800) * (interval == 'year' ? 9 : 1),
              'currency': 'jpy',
              'billing_total': plan == 'plus'
                  ? (interval == 'year' ? '16,200 JPY' : '1,800 JPY')
                  : (interval == 'year' ? '43,200 JPY' : '4,800 JPY'),
              'price_string': plan == 'plus'
                  ? (interval == 'year' ? '1,350 JPY/mo' : '1,800 JPY/mo')
                  : (interval == 'year' ? '3,600 JPY/mo' : '4,800 JPY/mo'),
              'is_active': plan == 'plus' && interval == 'month',
            },
      ],
    }).toJson(),
  );
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: Brightness.dark),
        locale: const Locale('ja'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: _Harness()),
      ),
    ),
  );
}
