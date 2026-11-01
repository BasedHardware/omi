import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';

String processingEstimateNumber(BuildContext context, double value) => (NumberFormat.decimalPattern(
      Localizations.localeOf(context).toLanguageTag(),
    )..maximumFractionDigits = 1)
        .format(value);

/// Half-up whole percent. 12.5 is 13, matching the backend wire value.
int processingWholePercent(double value) {
  if (!value.isFinite || value <= 0) return 0;
  return (value + 0.5).floor();
}

String processingPercentNumber(BuildContext context, double value) => (NumberFormat.decimalPattern(
      Localizations.localeOf(context).toLanguageTag(),
    )
          ..minimumFractionDigits = 0
          ..maximumFractionDigits = 0)
        .format(processingWholePercent(value));

/// A stable 10% of Free owners keep the previous held-recordings copy, so the personal
/// card's lift can be measured. Copy only: who can recover is the backend's paid check.
/// The bucket is computed on the device; analytics carries only the variant name.
bool heldAudioCopyHoldout([String? uid]) {
  String owner;
  try {
    owner = uid ?? SharedPreferencesUtil().uid;
  } catch (_) {
    return false;
  }
  if (owner.isEmpty) return false;
  final digest = sha256.convert(utf8.encode('held_audio_card_v1:$owner')).bytes;
  return ((digest[0] << 8) | digest[1]) % 100 < 10;
}

/// Free owners outside the holdout see the personal "safe but unprocessed" copy.
bool heldAudioPersonalCopy(BuildContext context) =>
    context.select<UsageProvider?, bool>((usage) => usage?.subscription?.subscription.plan == PlanType.basic) &&
    !heldAudioCopyHoldout();

/// Shared by the held-recordings card, live banner and Settings. Only the
/// server's waiting_choice state offers a funded-processing action.
class ProcessingBacklogView extends StatefulWidget {
  const ProcessingBacklogView({
    super.key,
    required this.backlog,
    required this.surface,
    required this.onUpgrade,
    this.onProcess,
    this.phoneAction,
  });

  final ProcessingBacklog backlog;
  final String surface;
  final VoidCallback onUpgrade;
  final Future<bool> Function()? onProcess;
  final Widget? phoneAction;

  @override
  State<ProcessingBacklogView> createState() => _ProcessingBacklogViewState();
}

class _ProcessingBacklogViewState extends State<ProcessingBacklogView> {
  bool _postponed = false;
  bool _busy = false;
  String? _seenState;

  HeldAudioCardSeenSurface get _surface => switch (widget.surface) {
        'b' => HeldAudioCardSeenSurface.live,
        'c' => HeldAudioCardSeenSurface.settings,
        _ => HeldAudioCardSeenSurface.home,
      };

  /// Null while the plan is unknown, so an unloaded subscription is never counted.
  HeldAudioCardSeenVariant? _variant() {
    final plan = context.read<UsageProvider?>()?.subscription?.subscription.plan;
    if (plan == null) return null;
    if (plan != PlanType.basic) return HeldAudioCardSeenVariant.paid;
    return heldAudioCopyHoldout() ? HeldAudioCardSeenVariant.holdout : HeldAudioCardSeenVariant.personal;
  }

  /// One exposure per surface and server state; rebuilds do not count again.
  void _recordSeen() {
    if (!mounted || !widget.backlog.isVisible || _seenState == widget.backlog.state) return;
    final variant = _variant();
    if (variant == null) return;
    _seenState = widget.backlog.state;
    final state = switch (widget.backlog.state) {
      'waiting_choice' => HeldAudioCardSeenState.waitingChoice,
      'processing' => HeldAudioCardSeenState.processing,
      _ => HeldAudioCardSeenState.capped,
    };
    const TypedEvents().emit(HeldAudioCardSeen(surface: _surface, variant: variant, state: state));
  }

  void _upgrade() {
    final variant = _variant();
    if (variant != null) {
      const TypedEvents().emit(HeldAudioUpgradeTapped(
        surface: HeldAudioUpgradeTappedSurface.values.byName(_surface.name),
        variant: HeldAudioUpgradeTappedVariant.values.byName(variant.name),
      ));
    }
    widget.onUpgrade();
  }

  @override
  void didUpdateWidget(ProcessingBacklogView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.backlog.state != widget.backlog.state) _postponed = false;
  }

  void _cancelDecision() {
    if (widget.onProcess == null) context.read<UsageProvider?>()?.cancelBacklogDecision();
  }

  void _postpone() {
    _cancelDecision();
    setState(() => _postponed = true);
  }

  Future<void> _process() async {
    if (_busy) return;
    final variant = _variant();
    if (variant != null) {
      const TypedEvents().emit(HeldAudioProcessTapped(
        surface: HeldAudioProcessTappedSurface.values.byName(_surface.name),
        variant: HeldAudioProcessTappedVariant.values.byName(variant.name),
      ));
    }
    var label = '';
    try {
      final backlog = widget.backlog;
      final l10n = context.l10n;
      label = l10n.processingAction;
      final confirmed = await showOmiConfirm(
        context,
        title: l10n.processingAction,
        message: [
          l10n.processingEstimate(
            processingEstimateNumber(context, backlog.estimatedHours),
            processingPercentNumber(context, backlog.estimatedPercent),
          ),
          if (backlog.exceedsRemaining) l10n.processingNewestFirst,
        ].join('\n\n'),
        confirmLabel: l10n.processingAction,
        cancelLabel: l10n.paywallNotNow,
      );
      if (!mounted) return;
      if (!confirmed) {
        _cancelDecision();
        return;
      }
      // An entitlement refresh may have changed the choice while the dialog was open.
      if (!widget.backlog.isWaitingChoice) return;
      if (widget.backlog.toJson().toString() != backlog.toJson().toString()) {
        // A changed estimate is a new decision: confirm it with a fresh identity.
        _cancelDecision();
        return _process();
      }
      setState(() => _busy = true);
      try {
        final success = await (widget.onProcess?.call() ?? context.read<UsageProvider>().processBacklog());
        if (!mounted) return;
        if (!success) OmiFeedback.error(context, l10n.somethingWentWrong);
      } finally {
        if (mounted) setState(() => _busy = false);
      }
    } catch (error, stack) {
      // The tap handler stays synchronous so the confirm dialog does not spin the
      // button. Failures still take OmiButton's reporter instead of the zone.
      OmiButton.reportOnPressedError(error, stack, label: label);
    }
  }

  @override
  Widget build(BuildContext context) {
    final backlog = widget.backlog;
    if (!backlog.isVisible) return const SizedBox.shrink();
    final canUpgrade = context.select<UsageProvider?, bool>(
      (usage) => usage?.subscription?.subscription.plan == PlanType.basic,
    );
    if (_seenState != backlog.state) WidgetsBinding.instance.addPostFrameCallback((_) => _recordSeen());
    final l10n = context.l10n;
    final duration = OmiDuration.compact(
      backlog.waitingSeconds,
      l10n,
    );
    // Free holds wait for an upgrade, not a choice; the holdout keeps the previous copy.
    final personal = backlog.isCapped && canUpgrade && !heldAudioCopyHoldout();
    final text = personal && backlog.waitingSeconds > 0
        ? l10n.processingFreeHeld(duration)
        : backlog.isCapped
            ? (backlog.budgetExhausted ? l10n.processingPaused : l10n.processingDeferred)
            : backlog.isProcessing
                ? l10n.processingProgress
                : l10n.processingWaiting(duration, processingPercentNumber(context, backlog.estimatedPercent));
    // With nothing waiting, a Free owner gets no line: there is nothing safe-but-unprocessed yet.
    final String? stored = !personal
        ? l10n.processingStored
        : backlog.waitingSeconds > 0
            ? l10n.processingFreeUpgrade
            : null;
    return Padding(
      padding: widget.surface == 'c'
          ? EdgeInsets.zero
          : const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: Key('processing_backlog_${widget.surface}'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 0.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(text, style: OmiType.headline),
            const SizedBox(height: OmiSpacing.xs),
            if (!backlog.isProcessing && stored != null)
              Text(stored, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            if (backlog.deferredConversations > 0) ...[
              const SizedBox(height: OmiSpacing.xs),
              Text(
                l10n.processingCount(backlog.deferredConversations),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ],
            if (backlog.isWaitingChoice && !_postponed) ...[
              const SizedBox(height: OmiSpacing.sm),
              OmiButton(
                maxLines: 2,
                key: Key('processing_backlog_process_${widget.surface}'),
                label: l10n.processingAction,
                expand: true,
                isLoading: _busy,
                // The button spins from [_busy] only after confirm. Returning
                // this Future would spin the label for the whole dialog.
                // [_process] reports failures through OmiButton.reportOnPressedError.
                onPressed: _busy
                    ? null
                    : () {
                        unawaited(_process());
                      },
              ),
              OmiButton.tertiary(
                key: Key('processing_backlog_not_now_${widget.surface}'),
                label: l10n.paywallNotNow,
                onPressed: _busy ? null : _postpone,
              ),
            ],
            if (canUpgrade) ...[
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                key: Key('processing_backlog_upgrade_${widget.surface}'),
                label: widget.surface == 'c' ? l10n.paywallComparePlans : l10n.upgrade,
                expand: true,
                onPressed: _upgrade,
              ),
            ],
            if (backlog.isCapped && widget.phoneAction != null) widget.phoneAction!,
          ],
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
