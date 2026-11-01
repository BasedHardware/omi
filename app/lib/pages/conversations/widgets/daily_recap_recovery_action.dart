import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/daily_summary_creation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/services/recap_events.dart';

typedef DailyRecapCreator = Future<ApiResult<DailySummary>> Function(String date);

/// One recovery flow shared by the recap list and the reachable notification
/// settings, including accounts with no recaps and notifications switched off.
class DailyRecapRecoveryAction extends StatefulWidget {
  const DailyRecapRecoveryAction({super.key, this.create, this.onCreated, this.settingsRow = false, this.now});

  final DailyRecapCreator? create;
  final Future<void> Function(DailySummary)? onCreated;
  final bool settingsRow;
  final DateTime Function()? now;

  @override
  State<DailyRecapRecoveryAction> createState() => _DailyRecapRecoveryActionState();
}

class _DailyRecapRecoveryActionState extends State<DailyRecapRecoveryAction> {
  bool _busy = false;
  bool _choosing = false;

  Future<void> _chooseDate() async {
    if (_busy || _choosing) return;
    _choosing = true;
    final clock = widget.now?.call() ?? DateTime.now();
    final today = DateTime(clock.year, clock.month, clock.day);
    DateTime? date;
    try {
      date = await showDatePicker(
        context: context,
        initialDate: today.subtract(const Duration(days: 1)),
        firstDate: DateTime(today.year - 1, today.month, today.day),
        lastDate: today,
        helpText: context.l10n.generateSummary,
      );
    } finally {
      _choosing = false;
    }
    if (!mounted || date == null) return;
    final key = '${date.year.toString().padLeft(4, '0')}-'
        '${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    await _recover(key);
  }

  Future<void> _recover(String date) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final result = await (widget.create ?? const DailySummaryCreationApi().create)(date);
      if (!mounted) return;
      switch (result) {
        case ApiSuccess<DailySummary>(:final data):
          announceRecapArrived();
          if (widget.onCreated != null) {
            await widget.onCreated!(data);
          } else {
            await Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => DailySummaryDetailPage(summaryId: data.id, summary: data),
            ));
          }
        case ApiFailure<DailySummary>(:final problem):
          final message = switch (problem.statusCode) {
            400 => context.l10n.recapRegenerateNoConversations,
            409 => '${context.l10n.processing}. ${context.l10n.recapRegenerateCooldown}',
            429 => context.l10n.recapRegenerateCooldown,
            422 => context.l10n.trySelectingDifferentDate,
            402 => context.l10n.upgradePlan,
            _ => switch (problem.kind) {
                ApiProblemKind.authTerminal => context.l10n.sessionExpiredSignInAgain,
                ApiProblemKind.transport => context.l10n.checkConnectionTryAgain,
                _ => context.l10n.somethingWentWrong,
              },
          };
          OmiFeedback.error(
            context,
            message,
            actionLabel: problem.retryable || problem.statusCode == 409 ? context.l10n.tryAgain : null,
            onAction: problem.retryable || problem.statusCode == 409 ? () => _recover(date) : null,
          );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final icon = _busy ? const OmiSpinner(size: OmiSpinnerSize.small) : const FaIcon(FontAwesomeIcons.calendarPlus);
    if (widget.settingsRow) {
      return OmiSettingsRow(
        leading: icon,
        title: context.l10n.generateSummary,
        showChevron: !_busy,
        onTap: _busy ? null : _chooseDate,
      );
    }
    return OmiIconButton(
      key: const Key('daily_recap_generate'),
      icon: icon,
      label: context.l10n.generateSummary,
      onPressed: _busy ? null : _chooseDate,
    );
  }
}
