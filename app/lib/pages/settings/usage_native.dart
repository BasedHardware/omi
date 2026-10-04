part of 'usage_page.dart';

extension _NativeUsagePresentation on _UsagePageState {
  Widget _nativeUsageSurface(Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    return Consumer<UsageProvider>(builder: (context, owner, _) {
      final l10n = context.l10n;
      final period = _getPeriodForIndex(_tabController.index);
      final stats = switch (period) {
        'today' => owner.todayUsage,
        'monthly' => owner.monthlyUsage,
        'yearly' => owner.yearlyUsage,
        _ => owner.allTimeUsage,
      };
      final history = switch (period) {
        'today' => owner.todayHistory,
        'monthly' => owner.monthlyHistory,
        'yearly' => owner.yearlyHistory,
        _ => owner.allTimeHistory,
      };
      final subscription = owner.subscription;
      final format = NumberFormat.decimalPattern(l10n.localeName);
      final buckets = usageBuckets(history ?? [], period, widget.debugNow ?? DateTime.now());
      final metrics = {
        UsageMetric.minutes.name: l10n.usageMinutes,
        UsageMetric.words.name: l10n.usageWords,
        UsageMetric.tasks.name: l10n.usageTasks,
        UsageMetric.memories.name: l10n.memories
      };
      final zero = stats == null ||
          stats.transcriptionSeconds == 0 &&
              stats.wordsTranscribed == 0 &&
              stats.insightsGained == 0 &&
              stats.memoriesCreated == 0;
      final stage = _fairUseStatus?['stage'];
      final stageLabel = switch (stage) {
        'warning' => l10n.fairUseStageWarning,
        'throttle' => l10n.fairUseStageThrottle,
        'restrict' => l10n.fairUseStageRestrict,
        _ => null,
      };
      final meters = <NativeRow>[];
      if (stats != null && subscription?.subscription.plan == PlanType.basic) {
        final sub = subscription!;
        if (sub.transcriptionSecondsLimit > 0) {
          final used = (sub.transcriptionSecondsUsed / 60).round();
          final limit = (sub.transcriptionSecondsLimit / 60).round();
          final ratio = (sub.transcriptionSecondsUsed / sub.transcriptionSecondsLimit).clamp(0.0, 1.0);
          meters.add(NativeRow('usage_minutes_quota', l10n.minsUsedThisMonth(format.format(used), limit),
              kind: 'progress', value: ratio, maximumValue: 1));
          if (ratio >= .8) {
            meters.add(NativeRow('usage_on_device', ratio >= 1 ? l10n.setupOnDevice : l10n.onDevice,
                subtitle: ratio >= 1 ? l10n.premiumMinutesUsed : l10n.premiumMinsLeft(limit - used),
                action: (_) => routeToPage(context, const TranscriptionSettingsPage())));
          }
        }
        if (sub.wordsTranscribedLimit > 0) {
          meters.add(NativeRow(
              'usage_words_quota',
              l10n.wordsUsedThisMonth(
                  format.format(sub.wordsTranscribedUsed), format.format(sub.wordsTranscribedLimit)),
              kind: 'progress',
              value: (sub.wordsTranscribedUsed / sub.wordsTranscribedLimit).clamp(0.0, 1.0),
              maximumValue: 1));
        }
        if (sub.insightsGainedLimit > 0) {
          meters.add(NativeRow('usage_insights_quota',
              l10n.insightsUsedThisMonth(format.format(sub.insightsGainedUsed), format.format(sub.insightsGainedLimit)),
              kind: 'progress',
              value: (sub.insightsGainedUsed / sub.insightsGainedLimit).clamp(0.0, 1.0),
              maximumValue: 1));
        }
      }
      if (stats != null && owner.chatQuotaUnit != null && period == 'monthly' && subscription != null) {
        final used = subscription.chatQuotaUsed;
        final limits = subscription.subscription.limits;
        final compute = subscription.chatQuotaUnit == 'cost_usd';
        final limit = compute ? limits.chatCostUsdPerMonth : limits.chatQuestionsPerMonth;
        final text = compute ? '\$${used.toStringAsFixed(2)}' : '${format.format(used.toInt())} ${l10n.chatTitle}';
        meters.add(NativeRow('usage_chat_quota', l10n.usageChatThisMonth,
            kind: limit != null && limit > 0 ? 'progress' : 'label',
            value: limit != null && limit > 0 ? (used / limit).clamp(0.0, 1.0) : null,
            maximumValue: limit != null && limit > 0 ? 1 : null,
            subtitle: limit == null || limit <= 0
                ? text
                : compute
                    ? l10n.chatUsedOfLimitCompute(used.toStringAsFixed(2), limit.toStringAsFixed(0))
                    : l10n.chatUsedOfLimitMessages(format.format(used.toInt()), format.format(limit))));
      }
      return Scaffold(
          body: IosNativeSurface(
        controller: _nativeUsage,
        title: l10n.planAndUsage,
        fallback: classic,
        loading: owner.isLoading,
        failed: owner.error != null,
        errorMessage: owner.error,
        onRefresh: (_) =>
            Future.wait([owner.fetchUsageStats(period: period), owner.fetchSubscription(), _loadFairUseStatus()]),
        toolbar: [
          NativeRow('usage_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('usage_share', l10n.share,
              symbol: 'square.and.arrow.up', enabled: stats != null, action: (_) => _shareUsage()),
        ],
        sections: [
          NativeSection('usage_period', [
            NativeRow('usage_period_choice', l10n.planAndUsage,
                kind: 'segmented',
                value: '${_tabController.index}',
                options: {'0': l10n.today, '1': l10n.usageMonth, '2': l10n.usageYear, '3': l10n.usageAll},
                action: (value) => _tabController.animateTo(int.parse(value as String)))
          ]),
          if (subscription != null && subscription.showSubscriptionUi)
            NativeSection('usage_plan', [
              NativeRow('usage_manage_plan', currentPlanDisplayName(context, subscription),
                  subtitle: subscription.subscription.plan.isPaid ? l10n.managePlan : l10n.basicPlanDescription,
                  symbol: 'creditcard',
                  action: (_) => _showPlansSheet())
            ]),
          if (stageLabel != null)
            NativeSection('usage_fair_use', [
              NativeRow('usage_fair_use_status', l10n.fairUseBannerStatus(stageLabel),
                  symbol: 'exclamationmark.circle', action: (_) => routeToPage(context, const FairUsePage()))
            ]),
          NativeSection('usage_stats', [
            if (zero && !owner.isLoading)
              NativeRow('usage_empty', l10n.noActivityYet,
                  kind: 'label', subtitle: l10n.startConversationToSeeInsights),
            if (!zero) ...[
              NativeRow('usage_listened', l10n.usageListened,
                  kind: 'label', subtitle: formatUsageDuration(stats.transcriptionSeconds)),
              NativeRow('usage_words', l10n.usageWordsHeard,
                  kind: 'label', subtitle: format.format(stats.wordsTranscribed)),
              NativeRow('usage_tasks', l10n.usageTasksNotes,
                  kind: 'label', subtitle: format.format(stats.insightsGained)),
              NativeRow('usage_memories', l10n.memories, kind: 'label', subtitle: format.format(stats.memoriesCreated)),
            ],
          ]),
          if (!zero && history?.isNotEmpty == true)
            NativeSection('usage_history', [
              NativeRow('usage_metric', l10n.planAndUsage,
                  kind: 'segmented',
                  value: _selectedMetric.name,
                  options: metrics,
                  action: (value) =>
                      _updateNativeUsage(() => _selectedMetric = UsageMetric.values.byName(value as String))),
              NativeRow('usage_chart', metrics[_selectedMetric.name]!, kind: 'chart', points: [
                for (var i = 0; i < buckets.points.length; i++)
                  if (!buckets.future[i])
                    {
                      'x': i.toDouble(),
                      'y': buckets.points[i] == null ? 0.0 : _selectedMetric.value(buckets.points[i]!),
                      'label': usageBucketLabel(buckets, period, i, l10n.localeName),
                    },
              ]),
              for (var i = 0; i < buckets.points.length; i++)
                if (!buckets.future[i] && buckets.points[i] != null)
                  NativeRow('usage_bucket:$i', usageBucketLabel(buckets, period, i, l10n.localeName),
                      kind: 'label',
                      subtitle:
                          '${format.format(_selectedMetric.value(buckets.points[i]!))} ${metrics[_selectedMetric.name]}'),
            ]),
          if (meters.isNotEmpty) NativeSection('usage_quotas', meters),
        ],
      ));
    });
  }
}
