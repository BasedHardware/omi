import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One unit per chart. The history endpoint supplies UTC hours for Today and
/// local calendar dates for Month and Year.
enum UsageMetric { minutes, words, tasks, memories }

extension UsageMetricValue on UsageMetric {
  double value(UsageHistoryPoint point) => switch (this) {
        UsageMetric.minutes => point.transcriptionSeconds / 60,
        UsageMetric.words => point.wordsTranscribed.toDouble(),
        UsageMetric.tasks => point.insightsGained.toDouble(),
        UsageMetric.memories => point.memoriesCreated.toDouble(),
      };
}

class UsageBuckets {
  const UsageBuckets(this.points, this.dates, this.future);
  final List<UsageHistoryPoint?> points;
  final List<DateTime> dates;
  final List<bool> future;

  int? peakIndex(UsageMetric metric) {
    int? best;
    for (var i = 0; i < points.length; i++) {
      if (future[i] || points[i] == null) continue;
      if (best == null || metric.value(points[i]!) > metric.value(points[best]!)) best = i;
    }
    return best;
  }
}

UsageBuckets usageBuckets(List<UsageHistoryPoint> history, String period, DateTime now,
    {DateTime Function(DateTime)? localize}) {
  DateTime decode(UsageHistoryPoint point) {
    final parsed = DateTime.parse(point.date);
    return period == 'today' ? (localize?.call(parsed) ?? parsed.toLocal()) : parsed;
  }

  if (period == 'all_time') {
    if (history.isEmpty) return const UsageBuckets([], [], []);
    final years = history.map((p) => decode(p).year);
    final first = years.reduce(math.min);
    final last = years.reduce(math.max);
    final byYear = {for (final p in history) decode(p).year: p};
    final dates = [for (var year = first; year <= last; year++) DateTime(year)];
    return UsageBuckets([for (final date in dates) byYear[date.year]], dates, List.filled(dates.length, false));
  }

  // Month/year history uses the server's calendar. Anchor slots to that
  // calendar even when the stored timezone fallback differs from this device.
  final anchor = history.isEmpty || period == 'today' ? now : decode(history.first);
  final count = switch (period) {
    'today' => 24,
    'monthly' => DateTime(anchor.year, anchor.month + 1, 0).day,
    _ => 12,
  };
  int index(DateTime date) => switch (period) {
        'today' => date.hour,
        'monthly' => date.day - 1,
        _ => date.month - 1,
      };
  final byIndex = <int, UsageHistoryPoint>{};
  for (final point in history) {
    final date = decode(point);
    final inPeriod = period == 'today'
        ? date.year == now.year && date.month == now.month && date.day == now.day
        : date.year == anchor.year && (period != 'monthly' || date.month == anchor.month);
    if (!inPeriod) continue;
    final slot = index(date);
    final previous = byIndex[slot];
    byIndex[slot] = previous == null
        ? point
        : UsageHistoryPoint(
            date: previous.date,
            transcriptionSeconds: previous.transcriptionSeconds + point.transcriptionSeconds,
            speechSeconds: previous.speechSeconds + point.speechSeconds,
            wordsTranscribed: previous.wordsTranscribed + point.wordsTranscribed,
            insightsGained: previous.insightsGained + point.insightsGained,
            memoriesCreated: previous.memoriesCreated + point.memoriesCreated,
          );
  }
  final dates = [
    for (var i = 0; i < count; i++)
      switch (period) {
        'today' => DateTime(now.year, now.month, now.day, i),
        'monthly' => DateTime(anchor.year, anchor.month, i + 1),
        _ => DateTime(anchor.year, i + 1),
      },
  ];
  return UsageBuckets(
    [for (var i = 0; i < count; i++) byIndex[i]],
    dates,
    [for (final date in dates) date.isAfter(now)],
  );
}

/// Pick the lowest axis cap from 2–3 intervals of 1/2/5 × 10^n.
(double, double) niceUsageScale(double peak) {
  if (peak <= 0) return (1, 2);
  final exponent = (math.log(peak) / math.ln10).floor();
  var bestStep = double.infinity;
  var bestMax = double.infinity;
  for (var power = exponent - 3; power <= exponent + 1; power++) {
    final magnitude = math.pow(10, power).toDouble();
    for (final multiple in [1.0, 2.0, 5.0]) {
      final step = multiple * magnitude;
      for (final intervals in [2, 3]) {
        final max = step * intervals;
        if (max >= peak && (max < bestMax || (max == bestMax && step > bestStep))) {
          bestStep = step;
          bestMax = max;
        }
      }
    }
  }
  return (bestStep, bestMax);
}

String formatUsageDuration(int seconds) {
  final minutes = (seconds / 60).round();
  final hours = minutes ~/ 60;
  if (hours >= 100) return '${(seconds / 3600).round()} h';
  if (hours == 0) return '${minutes}m';
  return '${hours}h ${minutes % 60}m';
}

String formatUsageCount(int value, String locale) => NumberFormat.compact(locale: locale).format(value);

class UsageChart extends StatelessWidget {
  const UsageChart(
      {super.key,
      required this.history,
      required this.period,
      required this.metric,
      required this.onMetricChanged,
      this.now,
      this.debugTooltipIndex});
  final List<UsageHistoryPoint> history;
  final String period;
  final UsageMetric metric;
  final ValueChanged<UsageMetric> onMetricChanged;
  final DateTime? now;
  @visibleForTesting
  final int? debugTooltipIndex;

  @override
  Widget build(BuildContext context) {
    final today = now ?? DateTime.now();
    final buckets = usageBuckets(history, period, today);
    final locale = context.l10n.localeName;
    final labels = [context.l10n.usageMinutes, context.l10n.usageWords, context.l10n.usageTasks, context.l10n.memories];
    final colors = [Colors.blue.shade300, Colors.green.shade300, Colors.orange.shade300, Colors.pink.shade200];
    final color = colors[metric.index];
    final peak = buckets.peakIndex(metric);
    final peakValue = peak == null ? 0.0 : metric.value(buckets.points[peak]!);
    final (tick, maxY) = niceUsageScale(peakValue);
    final unit = labels[metric.index].toLowerCase();
    String displayAmount(double amount, {bool compact = false, bool axis = false}) {
      if (metric == UsageMetric.minutes && amount > 0 && amount < 1) {
        final seconds = math.max(1, (amount * 60).round());
        return axis ? context.l10n.timeCompactSecs(seconds) : context.l10n.secondsCount(seconds);
      }
      final number = compact
          ? formatUsageCount(amount.round(), locale)
          : NumberFormat.decimalPattern(locale).format(amount.round());
      return axis ? number : '$number $unit';
    }

    final peakLabel = switch (period) {
      'today' => context.l10n.usagePeakHour,
      'monthly' => context.l10n.usageBestDay,
      'yearly' => context.l10n.usageBestMonth,
      _ => context.l10n.usageBestYear,
    };
    String dateLabel(int i) => switch (period) {
          'today' => DateFormat.j(locale).format(buckets.dates[i]),
          'monthly' => DateFormat.MMMd(locale).format(buckets.dates[i]),
          'yearly' => DateFormat.MMM(locale).format(buckets.dates[i]),
          _ => DateFormat.y(locale).format(buckets.dates[i]),
        };
    final groups = [
      for (var i = 0; i < buckets.points.length; i++)
        BarChartGroupData(x: i, barsSpace: 0, showingTooltipIndicators: i == debugTooltipIndex ? [0] : [], barRods: [
          BarChartRodData(
            toY: buckets.future[i]
                ? maxY * .035
                : buckets.points[i] == null
                    ? 0
                    : metric.value(buckets.points[i]!),
            width: period == 'monthly' || period == 'today' ? 7 : 16,
            color: buckets.future[i]
                ? Colors.transparent
                : i == peak
                    ? color
                    : color.withValues(alpha: .55),
            borderSide: buckets.future[i] ? BorderSide(color: OmiColors.border, width: 1) : BorderSide.none,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
          ),
        ]),
    ];
    return Container(
      key: const Key('usage_chart_card'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.sm, OmiSpacing.md, OmiSpacing.md, OmiSpacing.md),
      decoration: BoxDecoration(
          color: OmiColors.surface1, borderRadius: OmiRadius.lgAll, border: Border.all(color: OmiColors.border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 5, runSpacing: 2, children: [
          for (final choice in UsageMetric.values)
            Semantics(
              button: true,
              selected: metric == choice,
              label: labels[choice.index],
              child: InkWell(
                key: Key('metric_${choice.name}'),
                borderRadius: OmiRadius.pillAll,
                onTap: () => onMetricChanged(choice),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 44),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3),
                    child: Center(
                        widthFactor: 1,
                        heightFactor: 1,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                          decoration: BoxDecoration(
                              color:
                                  metric == choice ? colors[choice.index].withValues(alpha: .16) : OmiColors.surface2,
                              border: Border.all(
                                  color: metric == choice
                                      ? colors[choice.index].withValues(alpha: .55)
                                      : Colors.transparent),
                              borderRadius: OmiRadius.pillAll),
                          child: Row(mainAxisSize: MainAxisSize.min, children: [
                            if (metric == choice) ...[
                              Container(
                                  key: const Key('selected_metric_dot'),
                                  width: 7,
                                  height: 7,
                                  decoration: BoxDecoration(color: colors[choice.index], shape: BoxShape.circle)),
                              const SizedBox(width: 5),
                            ],
                            Text(labels[choice.index],
                                style: OmiType.caption.copyWith(
                                    color: metric == choice ? colors[choice.index] : OmiColors.textSecondary,
                                    fontWeight: FontWeight.w600)),
                          ]),
                        )),
                  ),
                ),
              ),
            ),
        ]),
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 5, 0, 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(peakLabel, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            Text(peak == null ? '—' : '${dateLabel(peak)} · ${displayAmount(peakValue, compact: true)}',
                style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis),
          ]),
        ),
        Semantics(
          label: '${labels[metric.index]}: ${[
            for (var i = 0; i < buckets.points.length; i++)
              if (!buckets.future[i])
                '${dateLabel(i)}, ${displayAmount(buckets.points[i] == null ? 0.0 : metric.value(buckets.points[i]!))}'
          ].join('; ')}',
          child: SizedBox(
              height: 165,
              child: BarChart(
                BarChartData(
                  minY: 0,
                  maxY: maxY,
                  barGroups: groups,
                  alignment: BarChartAlignment.spaceAround,
                  gridData: FlGridData(
                      show: true,
                      horizontalInterval: tick,
                      drawVerticalLine: false,
                      getDrawingHorizontalLine: (_) =>
                          FlLine(color: OmiColors.border.withValues(alpha: .5), strokeWidth: .5)),
                  extraLinesData: ExtraLinesData(horizontalLines: [
                    HorizontalLine(y: maxY, color: OmiColors.border.withValues(alpha: .5), strokeWidth: .5),
                  ]),
                  borderData: FlBorderData(show: false),
                  barTouchData: BarTouchData(
                    touchTooltipData: BarTouchTooltipData(
                      fitInsideVertically: true,
                      fitInsideHorizontally: true,
                      getTooltipColor: (_) => OmiColors.surface3,
                      getTooltipItem: (group, groupIndex, rod, rodIndex) {
                        if (buckets.future[group.x]) return null;
                        final amount = buckets.points[group.x] == null ? 0.0 : metric.value(buckets.points[group.x]!);
                        return BarTooltipItem('${dateLabel(group.x)}\n${displayAmount(amount)}', OmiType.footnote);
                      },
                    ),
                  ),
                  titlesData: FlTitlesData(
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    leftTitles: AxisTitles(
                        sideTitles: SideTitles(
                            showTitles: true,
                            reservedSize: 38,
                            interval: tick,
                            getTitlesWidget: (value, meta) => Text(displayAmount(value, compact: true, axis: true),
                                style: OmiType.caption.copyWith(color: OmiColors.textTertiary)))),
                    bottomTitles: AxisTitles(
                        sideTitles: SideTitles(
                            showTitles: true,
                            reservedSize: 22,
                            getTitlesWidget: (value, meta) {
                              final i = value.toInt();
                              if (i < 0 || i >= buckets.dates.length) return const SizedBox.shrink();
                              if (period == 'today' && i == today.hour) {
                                return Text(context.l10n.usageNow,
                                    style: OmiType.caption
                                        .copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.bold));
                              }
                              final show = period == 'today'
                                  ? i % 6 == 0
                                  : period == 'monthly'
                                      ? i % 7 == 0
                                      : period == 'yearly'
                                          ? i % 2 == 0
                                          : true;
                              if (!show) return const SizedBox.shrink();
                              return Text(
                                  period == 'today'
                                      ? DateFormat.j(locale).format(buckets.dates[i])
                                      : period == 'monthly'
                                          ? '${i + 1}'
                                          : period == 'yearly'
                                              ? DateFormat.MMM(locale).format(buckets.dates[i])
                                              : '${buckets.dates[i].year}',
                                  style: OmiType.caption.copyWith(color: OmiColors.textTertiary));
                            })),
                  ),
                ),
              )),
        ),
      ]),
    );
  }
}
