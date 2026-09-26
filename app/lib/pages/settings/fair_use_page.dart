import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class FairUsePage extends StatefulWidget {
  const FairUsePage({super.key});

  @override
  State<FairUsePage> createState() => _FairUsePageState();
}

class _FairUsePageState extends State<FairUsePage> {
  Map<String, dynamic>? _status;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final result = await getFairUseStatus();
      // Reconcile the rate-limit cooldown regardless of whether the widget is
      // still mounted — this only touches the SyncRateLimiter singleton and
      // must not be skipped if the user navigates away before the response
      // returns (otherwise a stale cooldown is never cleared).
      reconcileSyncRateLimitWithFairUseStatus(result);
      if (mounted) {
        if (result == null) {
          setState(() {
            _error = 'empty fair use status';
            _isLoading = false;
          });
        } else {
          setState(() {
            _status = result;
            _isLoading = false;
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.fairUsePolicy)),
      body: _isLoading
          ? const OmiLoadingState()
          : _error != null || _status == null
              ? OmiErrorState(message: context.l10n.fairUseLoadError, onRetry: _loadStatus)
              : RefreshIndicator(
                  onRefresh: _loadStatus,
                  child: SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildStatusBanner(),
                        _buildUsageSection(),
                        _buildBudgetSection(),
                        _buildMessageBanner(),
                        const SizedBox(height: OmiSpacing.xl),
                        _buildAboutFooter(),
                      ],
                    ),
                  ),
                ),
    );
  }

  Widget _buildStatusBanner() {
    final stage = _status!['stage'] as String? ?? 'none';
    if (stage == 'none') return const SizedBox.shrink();

    final caseRef = _status!['case_ref'] as String? ?? '';

    Color dotColor;
    String stageLabel;

    switch (stage) {
      case 'warning':
        dotColor = OmiColors.warning;
        stageLabel = context.l10n.fairUseStageWarning;
        break;
      case 'throttle':
        dotColor = OmiColors.warning;
        stageLabel = context.l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        dotColor = OmiColors.danger;
        stageLabel = context.l10n.fairUseStageRestrict;
        break;
      default:
        return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.xxs),
        constraints: const BoxConstraints(minHeight: 44),
        decoration: BoxDecoration(color: dotColor.withValues(alpha: 0.08), borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(stageLabel, style: OmiType.subhead.copyWith(color: dotColor, fontWeight: FontWeight.w500)),
            ),
            if (caseRef.isNotEmpty)
              Semantics(
                button: true,
                label: '${context.l10n.copy} $caseRef',
                excludeSemantics: true,
                child: InkWell(
                  borderRadius: OmiRadius.smAll,
                  onTap: () => OmiClipboard.copy(context, caseRef, what: caseRef),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(minHeight: 44),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            caseRef,
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontFamily: 'monospace'),
                          ),
                          const SizedBox(width: OmiSpacing.xxs),
                          const Icon(Icons.copy, size: 14, color: OmiColors.textSecondary),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildUsageSection() {
    final usagePct = _status!['usage_pct'] as Map<String, dynamic>? ?? {};
    final limits = _status!['limits'] as Map<String, dynamic>? ?? {};
    final speechToday = (_status!['speech_hours_today'] as num?)?.toDouble() ?? 0;
    final speech3day = (_status!['speech_hours_3day'] as num?)?.toDouble() ?? 0;
    final speechWeekly = (_status!['speech_hours_weekly'] as num?)?.toDouble() ?? 0;

    return Container(
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.fairUseSpeechUsage,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 16),
          _buildUsageBar(
            label: context.l10n.fairUseToday,
            hours: speechToday,
            limit: (limits['daily_hours'] as num?)?.toDouble() ?? 2.0,
            pct: (usagePct['daily'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 14),
          _buildUsageBar(
            label: context.l10n.fairUse3Day,
            hours: speech3day,
            limit: (limits['three_day_hours'] as num?)?.toDouble() ?? 8.0,
            pct: (usagePct['three_day'] as num?)?.toDouble() ?? 0,
          ),
          const SizedBox(height: 14),
          _buildUsageBar(
            label: context.l10n.fairUseWeekly,
            hours: speechWeekly,
            limit: (limits['weekly_hours'] as num?)?.toDouble() ?? 10.0,
            pct: (usagePct['weekly'] as num?)?.toDouble() ?? 0,
          ),
        ],
      ),
    );
  }

  Widget _buildUsageBar({required String label, required double hours, required double limit, required double pct}) {
    final barColor = pct >= 100
        ? OmiColors.danger
        : pct >= 80
            ? OmiColors.warning
            : OmiColors.accent;
    final l10n = context.l10n;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            Text(
              '${OmiDuration.compact((hours * 3600).round(), l10n)} / ${OmiDuration.compact((limit * 3600).round(), l10n)}',
              style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: const BorderRadius.all(Radius.circular(3)),
          child: LinearProgressIndicator(
            value: (pct / 100).clamp(0.0, 1.0),
            backgroundColor: OmiColors.surface3,
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
            minHeight: 4,
          ),
        ),
      ],
    );
  }

  Widget _buildBudgetSection() {
    final stage = _status!['stage'] as String? ?? 'none';
    if (stage != 'restrict') return const SizedBox.shrink();

    final dgBudget = _status!['dg_budget'] as Map<String, dynamic>?;
    if (dgBudget == null) return const SizedBox.shrink();

    final dailyLimitMs = (dgBudget['daily_limit_ms'] as num?)?.toInt() ?? 0;
    final usedMs = (dgBudget['used_ms'] as num?)?.toInt() ?? 0;
    final exhausted = dgBudget['exhausted'] as bool? ?? false;
    final resetsAt = dgBudget['resets_at'] as String? ?? '';

    if (dailyLimitMs <= 0) return const SizedBox.shrink();

    final usedMin = (usedMs / 60000).round();
    final limitMin = (dailyLimitMs / 60000).round();
    final pct = (usedMs / dailyLimitMs * 100).clamp(0.0, 100.0);
    final barColor = exhausted ? OmiColors.danger : OmiColors.accent;

    String resetLabel = '';
    if (resetsAt.isNotEmpty) {
      try {
        final resetTime = DateTime.parse(resetsAt);
        final now = DateTime.now().toUtc();
        final diff = resetTime.difference(now);
        if (diff.inMinutes > 0) {
          resetLabel = context.l10n.fairUseBudgetResetsAt(OmiDuration.compact(diff.inMinutes * 60, context.l10n));
        }
      } catch (_) {}
    }

    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: exhausted ? OmiColors.dangerSurface : OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Flexible(
                  child: Text(
                    context.l10n.fairUseDailyTranscription,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                  ),
                ),
                Text(
                  context.l10n.fairUseBudgetUsed('$usedMin', '$limitMin'),
                  style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: const BorderRadius.all(Radius.circular(3)),
              child: LinearProgressIndicator(
                value: (pct / 100).clamp(0.0, 1.0),
                backgroundColor: OmiColors.surface3,
                valueColor: AlwaysStoppedAnimation<Color>(barColor),
                minHeight: 4,
              ),
            ),
            if (exhausted) ...[
              const SizedBox(height: 10),
              Text(
                context.l10n.fairUseBudgetExhausted,
                style: OmiType.footnote.copyWith(color: OmiColors.danger, fontWeight: FontWeight.w500),
              ),
            ],
            if (resetLabel.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(resetLabel, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildMessageBanner() {
    final message = _status!['message'] as String? ?? '';
    if (message.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: OmiColors.textSecondary, size: 16),
            const SizedBox(width: 10),
            Expanded(
              child: Text(message, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.4)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAboutFooter() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.fairUseAboutTitle,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 4),
          Text(
            context.l10n.fairUseAboutBody,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.4),
          ),
        ],
      ),
    );
  }
}
