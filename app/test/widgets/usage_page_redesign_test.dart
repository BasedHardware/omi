import 'dart:async';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/settings/widgets/usage/usage_chart.dart';
import 'package:omi/providers/usage_provider.dart';

Widget app(Widget child, {UsageProvider? provider}) => ChangeNotifierProvider<UsageProvider>.value(
      value: provider ?? UsageProvider(),
      child: MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('en')],
        home: child,
      ),
    );

UsageStats stats({int seconds = 30720, int words = 44910}) => UsageStats(
      transcriptionSeconds: seconds,
      speechSeconds: 0,
      wordsTranscribed: words,
      insightsGained: 714,
      memoriesCreated: 60,
    );

UsageHistoryPoint point(String date, {int words = 10}) => UsageHistoryPoint(
      date: date,
      transcriptionSeconds: 120,
      speechSeconds: 0,
      wordsTranscribed: words,
      insightsGained: 3,
      memoriesCreated: 1,
    );

void main() {
  test('overlapping first timezone lookups send the resolved zone', () async {
    final zoneReady = Completer<String?>();
    final sentZones = <String?>[];
    final provider = UsageProvider(
      deviceTimeZone: () => zoneReady.future,
      usageRequest: ({required String period, required String? timeZone}) async {
        sentZones.add(timeZone);
        return UserUsageResponse(monthly: stats(), history: []);
      },
    );

    final fetch = provider.fetchUsageStats(period: 'monthly');
    final overlappingLookup = provider.refreshUsageTimeZone();
    zoneReady.complete('Asia/Tokyo');
    await Future.wait([fetch, overlappingLookup]);

    expect(sentZones, ['Asia/Tokyo']);
    expect(provider.monthlyUsage, isNotNull);
  });

  test('duration, compact number and nice scale', () {
    expect(formatUsageDuration(30720), '8h 32m');
    expect(formatUsageDuration(806400), '224 h');
    expect(formatUsageDuration(805740), '224 h');
    expect(formatUsageCount(44910, 'en'), '44.9K');
    expect(niceUsageScale(9600), (5000.0, 10000.0));
    expect(niceUsageScale(0), (1.0, 2.0));
  });

  test('all-time buckets have no padding years', () {
    final buckets = usageBuckets([point('2025-01-01'), point('2026-01-01')], 'all_time', DateTime(2026));
    expect(buckets.dates.map((d) => d.year), [2025, 2026]);
  });

  test('month and year slots follow returned history across a device date boundary', () {
    final month = usageBuckets([point('2026-12-31', words: 8)], 'monthly', DateTime(2027, 1, 1));
    expect(month.dates.length, 31);
    expect(month.dates.first, DateTime(2026, 12, 1));
    expect(month.points.last!.wordsTranscribed, 8);
    expect(month.future.last, isFalse);

    final year = usageBuckets([point('2026-12-01', words: 9)], 'yearly', DateTime(2027, 1, 1));
    expect(year.dates.first, DateTime(2026, 1, 1));
    expect(year.points.last!.wordsTranscribed, 9);
    expect(year.future.last, isFalse);
  });

  test('fall-back UTC hours add into the same local chart hour', () {
    final buckets = usageBuckets(
      [point('2026-11-01T08:00:00Z', words: 10), point('2026-11-01T09:00:00Z', words: 20)],
      'today',
      DateTime(2026, 11, 1, 12),
      localize: (_) => DateTime(2026, 11, 1, 1),
    );
    expect(buckets.points[1]!.wordsTranscribed, 30);
    expect(buckets.points[1]!.transcriptionSeconds, 240);
    expect(buckets.peakIndex(UsageMetric.words), 1);
  });

  testWidgets('chart switches its only metric; future slots are faint nonzero outlines', (tester) async {
    final now = DateTime(2026, 9, 26, 21);
    final history = [point('2026-09-01', words: 100), point('2026-09-08', words: 9600)];
    UsageMetric selected = UsageMetric.words;
    Future<void> pump() => tester.pumpWidget(app(StatefulBuilder(
        builder: (context, setState) => Scaffold(
              body: UsageChart(
                  history: history,
                  period: 'monthly',
                  metric: selected,
                  now: now,
                  onMetricChanged: (value) => setState(() => selected = value)),
            ))));
    await pump();
    final chart = tester.widget<BarChart>(find.byType(BarChart));
    expect(chart.data.barGroups.length, 30);
    expect(chart.data.barGroups[7].barRods.single.toY, 9600);
    expect(chart.data.barGroups[26].barRods.single.toY, greaterThan(0));
    expect(chart.data.barGroups[26].barRods.single.color, Colors.transparent);
    expect(chart.data.maxY, 10000);
    expect(chart.data.extraLinesData.horizontalLines.single.y, chart.data.maxY);
    expect(find.byKey(const Key('selected_metric_dot')), findsOneWidget);
    expect(tester.getSize(find.byKey(const Key('metric_words'))).height, greaterThanOrEqualTo(44));
    expect(chart.data.barTouchData.touchTooltipData.fitInsideVertically, isTrue);
    expect(chart.data.barTouchData.touchTooltipData.fitInsideHorizontally, isTrue);
    await tester.tap(find.byKey(const Key('metric_minutes')));
    await tester.pump();
    expect(selected, UsageMetric.minutes);
    final switched = tester.widget<BarChart>(find.byType(BarChart));
    expect(switched.data.barGroups[7].barRods.single.toY, 2);
  });

  testWidgets('sub-minute peak and axis use seconds', (tester) async {
    final history = [
      UsageHistoryPoint(
        date: '2026-09-01',
        transcriptionSeconds: 30,
        speechSeconds: 0,
        wordsTranscribed: 0,
        insightsGained: 0,
        memoriesCreated: 0,
      ),
    ];
    await tester.pumpWidget(app(Scaffold(
      body: UsageChart(
        history: history,
        period: 'monthly',
        metric: UsageMetric.minutes,
        now: DateTime(2026, 9, 26),
        onMetricChanged: (_) {},
      ),
    )));
    expect(find.textContaining('30 seconds'), findsOneWidget);
    expect(find.text('12s'), findsOneWidget);
    final chart = tester.widget<BarChart>(find.byType(BarChart));
    final tooltip = chart.data.barTouchData.touchTooltipData.getTooltipItem(
      chart.data.barGroups.first,
      0,
      chart.data.barGroups.first.barRods.first,
      0,
    );
    expect(tooltip!.text, contains('30 seconds'));
  });

  testWidgets('plan card is a child of the period scroll view', (tester) async {
    final provider = UsageProvider();
    final now = DateTime.now().toUtc();
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.architect, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ));
    provider.debugSetUsage('today', stats(), [point(now.toIso8601String())]);
    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.ancestor(of: find.text('Architect'), matching: find.byType(ListView)), findsWidgets);
    expect(find.byKey(const Key('usage_stat_grid')), findsOneWidget);
  });

  testWidgets('free plan keeps upgrade and all three usage meters', (tester) async {
    final provider = UsageProvider();
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 30720,
      transcriptionSecondsLimit: 36000,
      wordsTranscribedUsed: 44910,
      wordsTranscribedLimit: 60000,
      insightsGainedUsed: 714,
      insightsGainedLimit: 1000,
    ));
    provider.debugSetUsage('today', stats(), [point(DateTime.now().toUtc().toIso8601String())]);
    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Upgrade'), findsOneWidget);
    await tester.drag(find.byKey(const Key('usage_scroll_today')), const Offset(0, -500));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('of 600 min used this month', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('of 60,000 words used this month', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('of 1,000 insights gained this month', skipOffstage: false), findsOneWidget);
  });

  testWidgets('zero activity still shows free meters and monthly chat quota', (tester) async {
    final provider = UsageProvider();
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 36000,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 60000,
      insightsGainedUsed: 0,
      insightsGainedLimit: 1000,
      chatQuotaUsed: 2,
      chatQuotaUnit: 'questions',
    ));
    final zero = UsageStats(
      transcriptionSeconds: 0,
      speechSeconds: 0,
      wordsTranscribed: 0,
      insightsGained: 0,
      memoriesCreated: 0,
    );
    provider.debugSetUsage('today', zero, []);
    provider.debugSetUsage('monthly', zero, []);
    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byKey(const Key('usage_stat_grid')), findsNothing);
    expect(find.textContaining('of 600 min used this month', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('of 60,000 words used this month', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('of 1,000 insights gained this month', skipOffstage: false), findsOneWidget);
    expect(tester.getSize(find.byType(CupertinoSlidingSegmentedControl<int>)).height, greaterThanOrEqualTo(44));
    await tester.tap(find.text('Month').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Chat this month', skipOffstage: false), findsOneWidget);
  });

  testWidgets('month and year refetch with the new device timezone after a tab change', (tester) async {
    var zone = 'Asia/Tokyo';
    final requests = <(String, String?)>[];
    final provider = UsageProvider(
      deviceTimeZone: () async => zone,
      usageRequest: ({required String period, required String? timeZone}) async {
        requests.add((period, timeZone));
        return UserUsageResponse(
          monthly: period == 'monthly' ? stats() : null,
          yearly: period == 'yearly' ? stats() : null,
          allTime: period == 'all_time' ? stats() : null,
          history: [],
        );
      },
    );
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.architect, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ));
    provider.debugSetUsage('today', stats(), []);
    await provider.fetchUsageStats(period: 'monthly');
    await provider.fetchUsageStats(period: 'yearly');
    await provider.fetchUsageStats(period: 'all_time');

    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Month').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.length, 3); // Cached month did not refetch.

    zone = 'America/Los_Angeles';
    await tester.tap(find.text('Year').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.last, ('yearly', zone));
    expect(provider.monthlyUsage, isNull);
    expect(provider.allTimeUsage, isNotNull);

    await tester.tap(find.text('Month').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.last, ('monthly', zone));
    expect(provider.monthlyUsage, isNotNull);

    zone = 'Asia/Kolkata';
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(requests.last, ('monthly', zone));
  });

  testWidgets('calendar rollover expires cached day, month, and year on resume and tab select', (tester) async {
    var now = DateTime(2026, 9, 30, 23, 59);
    final requests = <String>[];
    final provider = UsageProvider(
      now: () => now,
      deviceTimeZone: () async => 'Asia/Tokyo',
      usageRequest: ({required String period, required String? timeZone}) async {
        requests.add(period);
        return UserUsageResponse(today: stats(), monthly: stats(), yearly: stats(), history: []);
      },
    );
    await provider.fetchUsageStats(period: 'today');
    await provider.fetchUsageStats(period: 'monthly');
    await provider.fetchUsageStats(period: 'yearly');
    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Month').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests, ['today', 'monthly', 'yearly']);

    now = DateTime(2026, 10, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.last, 'monthly');
    expect(requests.length, 4);
    await tester.tap(find.text('Today').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.last, 'today');
    expect(requests.length, 5);

    now = DateTime(2027, 1, 1);
    await tester.tap(find.text('Year').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests.last, 'yearly');
    expect(requests.length, 6);
  });

  testWidgets('calendar rollover keeps cached All time on resume', (tester) async {
    var now = DateTime(2026, 9, 30, 23, 59);
    var zone = 'Asia/Tokyo';
    final requests = <String>[];
    final provider = UsageProvider(
      now: () => now,
      deviceTimeZone: () async => zone,
      usageRequest: ({required String period, required String? timeZone}) async {
        requests.add(period);
        return UserUsageResponse(today: stats(), allTime: stats(), history: []);
      },
    );
    await provider.fetchUsageStats(period: 'today');
    await provider.fetchUsageStats(period: 'all_time');
    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('All time').first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests, ['today', 'all_time']);

    now = DateTime(2026, 10, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(provider.todayUsage, isNull);
    expect(provider.allTimeUsage, isNotNull);
    expect(requests, ['today', 'all_time']);

    zone = 'America/Los_Angeles';
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(requests, ['today', 'all_time', 'all_time']);
  });

  testWidgets('a usage load failure still shows plan management when subscription loaded', (tester) async {
    final provider = UsageProvider(
      deviceTimeZone: () async => 'UTC',
      usageRequest: ({required String period, required String? timeZone}) async => null,
    );
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.architect, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    ));
    await provider.fetchUsageStats(period: 'today');

    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));

    // The error state is showing (no usage data loaded)...
    expect(find.text('Failed to load usage data. Please try again later.'), findsOneWidget);
    // ...but the plan card, and its path to management/cancellation, stays reachable (#20621).
    expect(find.text('Architect'), findsOneWidget);
    expect(find.text('Manage Plan'), findsOneWidget);
  });

  testWidgets('a usage load failure with no subscription loaded shows only the error', (tester) async {
    final provider = UsageProvider(
      deviceTimeZone: () async => 'UTC',
      usageRequest: ({required String period, required String? timeZone}) async => null,
    );
    await provider.fetchUsageStats(period: 'today');

    await tester.pumpWidget(app(const UsagePage(debugSkipFetch: true), provider: provider));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Failed to load usage data. Please try again later.'), findsOneWidget);
    expect(find.text('Manage Plan'), findsNothing);
  });
}
