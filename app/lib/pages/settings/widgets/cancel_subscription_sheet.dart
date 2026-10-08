import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/widgets/leave_flow_widgets.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/other/temp.dart';

const _stepCount = 3;
const _detailsLength = 300;

/// Subscription cancellation: reason → feedback → consequences. A pushed page, not a sheet; each
/// step is its own route, so the iOS edge swipe and system back step back one step. This widget
/// is step 1 and owns the flow; [show] resolves `true` when the subscription was cancelled.
class CancelSubscriptionFlow extends StatefulWidget {
  const CancelSubscriptionFlow({super.key});

  static Future<bool?> show(BuildContext context) {
    return Navigator.of(context).push<bool>(omiPageRoute(builder: (_) => const CancelSubscriptionFlow()));
  }

  @override
  State<CancelSubscriptionFlow> createState() => _CancelSubscriptionFlowState();
}

/// What the reader has entered so far, shared by the three steps.
class _CancelFlow {
  final exit = LeaveFlowExit();
  final details = TextEditingController();
  String? reason;

  void dispose() => details.dispose();
}

class _CancelSubscriptionFlowState extends State<CancelSubscriptionFlow> {
  final _flow = _CancelFlow();

  static const _reasons = [
    _Reason('too_expensive', FontAwesomeIcons.wallet),
    _Reason('not_using_enough', FontAwesomeIcons.clock),
    _Reason('missing_features', FontAwesomeIcons.puzzlePiece),
    _Reason('audio_quality', FontAwesomeIcons.microphone),
    _Reason('battery_drain', FontAwesomeIcons.batteryQuarter),
    _Reason('found_alternative', FontAwesomeIcons.arrowRightArrowLeft),
    _Reason('other', FontAwesomeIcons.ellipsis),
  ];

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.subscriptionCancelFlowStarted();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _flow.exit.attach(context);
  }

  @override
  void dispose() {
    _flow.dispose();
    super.dispose();
  }

  String _label(String key) => switch (key) {
        'too_expensive' => context.l10n.cancelReasonTooExpensive,
        'not_using_enough' => context.l10n.cancelReasonNotUsing,
        'missing_features' => context.l10n.cancelReasonMissingFeatures,
        'audio_quality' => context.l10n.cancelReasonAudioQuality,
        'battery_drain' => context.l10n.cancelReasonBatteryDrain,
        'found_alternative' => context.l10n.cancelReasonFoundAlternative,
        'other' => context.l10n.cancelReasonOther,
        _ => key,
      };

  void _onPopInvoked(bool didPop) {
    if (didPop && !_flow.exit.finished) {
      PlatformManager.instance.analytics.subscriptionCancelAbandoned(step: 1, reason: _flow.reason);
    }
  }

  void _continue() {
    final reason = _flow.reason;
    if (reason == null) return;
    PlatformManager.instance.analytics.subscriptionCancelReasonSelected(reason: reason);
    routeToPage(context, _CancelFeedbackStep(flow: _flow));
  }

  @override
  Widget build(BuildContext context) {
    final reason = _flow.reason;
    final fallback = LeaveFlowStepScaffold(
      step: 0,
      stepCount: _stepCount,
      title: context.l10n.whyAreYouCanceling,
      subtitle: context.l10n.cancelReasonSubtitle,
      onPopInvoked: _onPopInvoked,
      body: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        itemCount: _reasons.length,
        separatorBuilder: (_, __) => const SizedBox(height: OmiSpacing.xs),
        itemBuilder: (_, i) => LeaveFlowReasonTile(
          icon: _reasons[i].icon,
          label: _label(_reasons[i].key),
          selected: reason == _reasons[i].key,
          onTap: () => setState(() => _flow.reason = _reasons[i].key),
        ),
      ),
      actions: OmiButton(
        label: context.l10n.continueButton,
        expand: true,
        onPressed: reason == null ? null : _continue,
      ),
    );
    return nativeLeaveStep(
      context,
      step: 0,
      stepCount: _stepCount,
      title: context.l10n.whyAreYouCanceling,
      subtitle: context.l10n.cancelReasonSubtitle,
      canPop: true,
      onPopInvoked: _onPopInvoked,
      fallback: fallback,
      sections: [
        NativeSection('cancel_reasons', [
          for (final option in _reasons)
            NativeRow('cancel_reason:${option.key}', _label(option.key),
                symbol: reason == option.key ? 'checkmark.circle.fill' : 'circle',
                action: (_) => setState(() => _flow.reason = option.key)),
        ]),
        NativeSection('cancel_reason_actions', [
          NativeRow('leave_continue', context.l10n.continueButton, enabled: reason != null, action: (_) => _continue()),
        ]),
      ],
    );
  }
}

class _CancelFeedbackStep extends StatelessWidget {
  const _CancelFeedbackStep({required this.flow});

  final _CancelFlow flow;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final title = switch (flow.reason) {
      'too_expensive' => l10n.feedbackTitleTooExpensive,
      'missing_features' => l10n.feedbackTitleMissingFeatures,
      'audio_quality' => l10n.feedbackTitleAudioQuality,
      'battery_drain' => l10n.feedbackTitleBatteryDrain,
      'found_alternative' => l10n.feedbackTitleFoundAlternative,
      'not_using_enough' => l10n.feedbackTitleNotUsing,
      _ => l10n.tellUsMore,
    };
    final subtitle = switch (flow.reason) {
      'too_expensive' => l10n.feedbackSubtitleTooExpensive,
      'missing_features' => l10n.feedbackSubtitleMissingFeatures,
      'audio_quality' => l10n.feedbackSubtitleAudioQuality,
      'battery_drain' => l10n.feedbackSubtitleBatteryDrain,
      'found_alternative' => l10n.feedbackSubtitleFoundAlternative,
      'not_using_enough' => l10n.feedbackSubtitleNotUsing,
      _ => l10n.cancelReasonDetailHint,
    };
    void next() => routeToPage(context, _CancelConfirmStep(flow: flow));

    final fallback = LeaveFlowStepScaffold(
      step: 1,
      stepCount: _stepCount,
      title: title,
      subtitle: subtitle,
      body: Align(
        alignment: Alignment.topCenter,
        child: SingleChildScrollView(child: LeaveFlowTextField(controller: flow.details, maxLength: _detailsLength)),
      ),
      actions: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiButton(label: l10n.continueButton, expand: true, onPressed: next),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(label: l10n.skipForNow, expand: true, onPressed: next),
        ],
      ),
    );
    if (!nativePresentationEnabled) return fallback;
    // Rebuilds with every native edit, so the next snapshot carries the current text.
    return ListenableBuilder(
      listenable: flow.details,
      builder: (context, _) => nativeLeaveStep(
        context,
        step: 1,
        stepCount: _stepCount,
        title: title,
        subtitle: subtitle,
        canPop: true,
        fallback: fallback,
        sections: [
          NativeSection('cancel_feedback', [
            NativeRow('cancel_details', l10n.cancelReasonDetailHint,
                kind: 'text',
                value: nativeLeaveText(flow.details.text, _detailsLength),
                maximumLength: _detailsLength,
                action: (value) => flow.details.text = value as String),
          ]),
          NativeSection('cancel_feedback_actions', [
            NativeRow('leave_continue', l10n.continueButton, action: (_) {
              next();
            }),
            NativeRow('leave_skip', l10n.skipForNow, action: (_) {
              next();
            }),
          ]),
        ],
      ),
    );
  }
}

class _CancelConfirmStep extends StatefulWidget {
  const _CancelConfirmStep({required this.flow});

  final _CancelFlow flow;

  @override
  State<_CancelConfirmStep> createState() => _CancelConfirmStepState();
}

class _CancelConfirmStepState extends State<_CancelConfirmStep> {
  bool _isCancelling = false;

  _CancelFlow get _flow => widget.flow;

  Future<void> _confirmCancel() async {
    setState(() => _isCancelling = true);
    final provider = context.read<UsageProvider>();
    final details = _flow.details.text.trim().isNotEmpty ? _flow.details.text.trim() : null;
    final attempt =
        ProductTelemetry.instance.start(ProductJourney.subscriptionCancel, surface: ProductSurface.settings);
    PlatformManager.instance.analytics.subscriptionCancelConfirmed(reason: _flow.reason!, details: details);

    // The native view shows a blocking activity while the owner works; it closes before any feedback.
    final activity = await leaveFlowActivity(context, context.l10n.cancelling);
    try {
      final bool success;
      try {
        success = await provider.cancelUserSubscription(reason: _flow.reason, reasonDetails: details);
      } finally {
        await activity?.dismiss();
      }
      if (!mounted) return;
      if (success) {
        attempt.complete(ProductOutcome.success);
        OmiFeedback.confirm(context, context.l10n.subscriptionSetToCancel);
        _flow.exit.close(context, true);
      } else {
        attempt.complete(ProductOutcome.failure, failure: ProductFailure.server);
        OmiFeedback.error(context, context.l10n.failedToCancelSubscription);
        setState(() => _isCancelling = false);
      }
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.network);
      if (mounted) {
        OmiFeedback.error(
          context,
          context.l10n.anErrorOccurredTryAgain,
          actionLabel: context.l10n.tryAgain,
          onAction: () {
            if (mounted && !_isCancelling) _confirmCancel();
          },
        );
        setState(() => _isCancelling = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final sub = context.read<UsageProvider>().subscription?.subscription;
    final periodEnd = sub?.currentPeriodEnd;
    final renewalDate =
        periodEnd == null ? '' : OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(periodEnd * 1000));
    void keep() {
      PlatformManager.instance.analytics.subscriptionCancelKeptPlan(step: 3, reason: _flow.reason);
      _flow.exit.close(context, false);
    }

    final fallback = LeaveFlowStepScaffold(
      step: 2,
      stepCount: _stepCount,
      title: context.l10n.justAMoment,
      subtitle: context.l10n.cancelConsequencesSubtitle,
      canPop: !_isCancelling,
      body: Column(
        children: [
          LeaveFlowNotice(
            icon: FontAwesomeIcons.circleInfo,
            text: context.l10n.cancelBillingPeriodInfo(renewalDate),
            color: OmiColors.warning,
          ),
          const SizedBox(height: OmiSpacing.md),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
              children: [
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.infinity, text: context.l10n.cancelConsequenceNoAccess),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.bolt, text: context.l10n.cancelConsequenceBattery),
                LeaveFlowConsequenceRow(
                  icon: FontAwesomeIcons.solidComments,
                  text: context.l10n.cancelConsequenceQuality,
                ),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.gaugeHigh, text: context.l10n.cancelConsequenceDelay),
                LeaveFlowConsequenceRow(icon: FontAwesomeIcons.userGroup, text: context.l10n.cancelConsequenceSpeakers),
                LeaveFlowConsequenceRow(
                  icon: FontAwesomeIcons.phone,
                  text: context.l10n.cancelConsequencePhoneCalls,
                ),
              ],
            ),
          ),
        ],
      ),
      actions: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiButton(
            label: context.l10n.keepSubscription,
            expand: true,
            onPressed: _isCancelling ? null : keep,
          ),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.destructive(
            label: context.l10n.cancelSubscription,
            expand: true,
            isLoading: _isCancelling,
            onPressed: _confirmCancel,
          ),
        ],
      ),
    );
    final l10n = context.l10n;
    return nativeLeaveStep(
      context,
      step: 2,
      stepCount: _stepCount,
      title: l10n.justAMoment,
      subtitle: l10n.cancelConsequencesSubtitle,
      canPop: !_isCancelling,
      fallback: fallback,
      sections: [
        NativeSection('cancel_consequences', [
          NativeRow('cancel_period', l10n.cancelBillingPeriodInfo(renewalDate), kind: 'label', symbol: 'info.circle'),
          NativeRow('cancel_no_access', l10n.cancelConsequenceNoAccess, kind: 'label', symbol: 'infinity'),
          NativeRow('cancel_battery', l10n.cancelConsequenceBattery, kind: 'label', symbol: 'bolt'),
          NativeRow('cancel_quality', l10n.cancelConsequenceQuality,
              kind: 'label', symbol: 'bubble.left.and.bubble.right'),
          NativeRow('cancel_delay', l10n.cancelConsequenceDelay, kind: 'label', symbol: 'speedometer'),
          NativeRow('cancel_speakers', l10n.cancelConsequenceSpeakers, kind: 'label', symbol: 'person.2'),
          NativeRow('cancel_phone_calls', l10n.cancelConsequencePhoneCalls, kind: 'label', symbol: 'phone'),
        ]),
        NativeSection('cancel_actions', [
          NativeRow('cancel_keep', l10n.keepSubscription, enabled: !_isCancelling, action: (_) => keep()),
          NativeRow('cancel_confirm', l10n.cancelSubscription,
              subtitle: _isCancelling ? l10n.cancelling : '',
              destructive: true,
              enabled: !_isCancelling, action: (_) async {
            if (!_isCancelling) await _confirmCancel();
          }),
        ]),
      ],
    );
  }
}

class _Reason {
  final String key;
  final FaIconData icon;
  const _Reason(this.key, this.icon);
}
