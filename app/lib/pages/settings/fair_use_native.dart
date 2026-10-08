part of 'fair_use_page.dart';

extension _NativeFairUsePresentation on _FairUsePageState {
  Widget _nativeFairUseSurface(Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    final l10n = context.l10n;
    final status = _status;
    final rows = <NativeRow>[];
    if (status != null) {
      final stage = status['stage'] as String? ?? 'none';
      final label = switch (stage) {
        'warning' => l10n.fairUseStageWarning,
        'throttle' => l10n.fairUseStageThrottle,
        'restrict' => l10n.fairUseStageRestrict,
        _ => null,
      };
      if (label != null) {
        rows.add(NativeRow('fair_use_stage', label, kind: 'label'));
        final reference = status['case_ref'] as String? ?? '';
        if (reference.isNotEmpty) {
          rows.add(NativeRow('fair_use_reference', reference,
              symbol: 'doc.on.doc', action: (_) => OmiClipboard.copy(context, reference, what: reference)));
        }
      }
      final usage = status['usage_pct'] as Map<String, dynamic>? ?? {};
      final limits = status['limits'] as Map<String, dynamic>? ?? {};
      for (final (id, title, hoursKey, limitKey, defaultLimit) in [
        ('daily', l10n.fairUseToday, 'speech_hours_today', 'daily_hours', 2.0),
        ('three_day', l10n.fairUse3Day, 'speech_hours_3day', 'three_day_hours', 8.0),
        ('weekly', l10n.fairUseWeekly, 'speech_hours_weekly', 'weekly_hours', 10.0),
      ]) {
        final hours = (status[hoursKey] as num?)?.toDouble() ?? 0;
        final limit = (limits[limitKey] as num?)?.toDouble() ?? defaultLimit;
        rows.add(NativeRow('fair_use_$id', title,
            kind: 'progress',
            maximumValue: 100,
            value: ((usage[id] as num?)?.toDouble() ?? 0).clamp(0, 100),
            subtitle: '${OmiDuration.compact((hours * 3600).round(), l10n)} / '
                '${OmiDuration.compact((limit * 3600).round(), l10n)}'));
      }
      final budget = status['dg_budget'] as Map<String, dynamic>?;
      final dailyLimit = (budget?['daily_limit_ms'] as num?)?.toInt() ?? 0;
      if (stage == 'restrict' && budget != null && dailyLimit > 0) {
        final used = (budget['used_ms'] as num?)?.toInt() ?? 0;
        rows.add(NativeRow('fair_use_budget', l10n.fairUseDailyTranscription,
            kind: 'progress',
            maximumValue: 100,
            value: (used / dailyLimit * 100).clamp(0, 100),
            subtitle: l10n.fairUseBudgetUsed('${(used / 60000).round()}', '${(dailyLimit / 60000).round()}')));
        if (budget['exhausted'] == true) {
          rows.add(NativeRow('fair_use_exhausted', l10n.fairUseBudgetExhausted, kind: 'label'));
        }
        final resets = DateTime.tryParse(budget['resets_at'] as String? ?? '');
        final minutes = resets?.difference(DateTime.now().toUtc()).inMinutes ?? 0;
        if (minutes > 0) {
          rows.add(NativeRow('fair_use_reset', l10n.fairUseBudgetResetsAt(OmiDuration.compact(minutes * 60, l10n)),
              kind: 'label'));
        }
      }
      final message = status['message'] as String? ?? '';
      if (message.isNotEmpty) rows.add(NativeRow('fair_use_message', message, kind: 'label'));
    }
    return Scaffold(
        body: IosNativeSurface(
            title: l10n.fairUsePolicy,
            fallback: classic,
            loading: _isLoading,
            failed: _error != null || !_isLoading && status == null,
            errorMessage: l10n.fairUseLoadError,
            onRefresh: (_) => _loadStatus(),
            toolbar: [
          NativeRow('fair_use_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop())
        ],
            sections: [
          NativeSection('fair_use_status', rows, title: l10n.fairUseSpeechUsage),
          NativeSection('fair_use_about', [NativeRow('fair_use_about_text', l10n.fairUseAboutBody, kind: 'label')],
              title: l10n.fairUseAboutTitle)
        ]));
  }
}
