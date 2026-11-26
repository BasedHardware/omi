import 'dart:async';

import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Home offers the choice only when the server reports room for waiting recordings.
class ProcessingBacklogChoiceCard extends StatelessWidget {
  const ProcessingBacklogChoiceCard({super.key});

  void _openConfirmation(BuildContext context, ProcessingBacklog backlog, String percent) {
    if (!context.mounted) return;
    final label = context.l10n.processingAction;
    unawaited(_confirm(context, backlog, percent).catchError((Object error, StackTrace stack) {
      OmiButton.reportOnPressedError(error, stack, label: label);
    }));
  }

  Future<void> _confirm(BuildContext context, ProcessingBacklog backlog, String percent) async {
    final usage = context.read<UsageProvider>();
    if (usage.isProcessingBacklog || !identical(usage.subscription?.processingBacklog, backlog)) return;
    final l10n = context.l10n;
    final hours = NumberFormat.decimalPattern(Localizations.localeOf(context).toLanguageTag())
      ..maximumFractionDigits = 1;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.processingAction,
      message: [
        l10n.processingEstimate(hours.format(backlog.estimatedHours), percent),
        if (backlog.exceedsRemaining) l10n.processingNewestFirst,
      ].join('\n\n'),
      confirmLabel: l10n.processingAction,
      cancelLabel: l10n.paywallNotNow,
    );
    if (!context.mounted ||
        !identical(context.read<UsageProvider?>(), usage) ||
        !identical(usage.subscription?.processingBacklog, backlog)) {
      return;
    }
    if (!confirmed) {
      usage.cancelBacklogDecision();
      return;
    }
    final success = await usage.processBacklog();
    if (!context.mounted) return;
    if (success && usage.subscription?.processingBacklog?.isProcessing == true) {
      OmiFeedback.confirm(context, l10n.processingProgress);
    } else if (!success && identical(usage.subscription?.processingBacklog, backlog)) {
      OmiFeedback.error(
        context,
        l10n.somethingWentWrong,
        actionLabel: l10n.tryAgain,
        onAction: () => _openConfirmation(context, backlog, percent),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final (backlog, submitting) = context.select<UsageProvider?, (ProcessingBacklog?, bool)>(
      (usage) => (usage?.subscription?.processingBacklog, usage?.isProcessingBacklog ?? false),
    );
    if (backlog == null || !backlog.isWaitingChoice) {
      return const SizedBox.shrink();
    }
    final l10n = context.l10n;
    final percent = (NumberFormat.decimalPattern(Localizations.localeOf(context).toLanguageTag())
          ..maximumFractionDigits = 0)
        .format(backlog.estimatedPercent.round());
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: DecoratedBox(
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                l10n.processingWaiting(OmiDuration.long(backlog.waitingSeconds, l10n), percent),
                style: OmiType.subhead,
              ),
              const SizedBox(height: OmiSpacing.sm),
              OmiButton.secondary(
                key: const Key('processing_backlog_process'),
                label: l10n.processingAction,
                expand: true,
                isLoading: submitting,
                maxLines: null,
                onPressed: submitting ? null : () => _openConfirmation(context, backlog, percent),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ProcessingDeferredMarker extends StatelessWidget {
  const ProcessingDeferredMarker({super.key});

  @override
  Widget build(BuildContext context) => Text(
        context.l10n.processingDeferred,
        key: const Key('processing_deferred_marker'),
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
      );
}
