import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

/// Usage already on hand: nothing is fetched, so the page shows exactly what was seeded.
class _SeededUsage extends UsageProvider {
  @override
  Future<void> fetchUsageStats({required String period}) async {}
  @override
  Future<void> fetchSubscription() async {}
  @override
  Future<void> loadAvailablePlans() async {}
}

UsageStats _stats(int minutes) => UsageStats(
      transcriptionSeconds: minutes * 60,
      speechSeconds: minutes * 60,
      wordsTranscribed: minutes * 150,
      insightsGained: 3,
      memoriesCreated: 5,
    );

/// v2 Plan & usage: the period is a segmented control under the plan, not tabs in the header.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('Today · This Month · This Year · All Time switch the stats shown', (tester) async {
    final usage = _SeededUsage()
      ..debugSetUsageStats('today', _stats(12))
      ..debugSetUsageStats('monthly', _stats(400));
    addTearDown(usage.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: UsagePage(),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(TabBar), findsNothing);
    final period = find.byKey(const Key('usage_period'));
    expect(period, findsOneWidget);
    expect(tester.widget<OmiSegmentedControl<int>>(period).selected, 0);
    expect(find.text('12m'), findsOneWidget);

    await tester.tap(find.descendant(of: period, matching: find.text('This Month')));
    await tester.pumpAndSettle();
    expect(tester.widget<OmiSegmentedControl<int>>(period).selected, 1);
    expect(find.text('6h 40m'), findsOneWidget);
  });
}
