import 'dart:async';

import 'package:flutter/material.dart';
import 'package:in_app_review/in_app_review.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Setting up your Omi": the last moment before the completion screen. A short checklist ticks
/// through the personalization steps while any setup the flow started earlier ([pendingWork])
/// finishes, then the page advances itself through [onFinished].
///
/// [ratingPromptDelay] after the page appears, a native-style alert asks whether Omi has been nice
/// to use; "Yes" opens the platform's in-app review sheet ([requestReview]), "Not really" just
/// closes. The page never advances while that alert is open.
///
/// Shown only behind [OnboardingSetupRatingPromptGate]; the wrapper owns that decision.
class OnboardingSetupPage extends StatefulWidget {
  const OnboardingSetupPage({
    super.key,
    required this.onFinished,
    this.pendingWork,
    this.stepInterval = const Duration(milliseconds: 750),
    this.ratingPromptDelay = const Duration(milliseconds: 1200),
    this.maxPendingWait = const Duration(seconds: 5),
    this.requestReview,
  });

  /// Called once, after the last tick and once [pendingWork] settled (or [maxPendingWait] ran out).
  final VoidCallback onFinished;

  /// Setup the flow already started (the knowledge-graph prebuild); null means nothing to wait for.
  final Future<void>? pendingWork;

  /// Gap between two ticks.
  final Duration stepInterval;

  /// Delay from the first frame to the rating alert.
  final Duration ratingPromptDelay;

  /// Longest the page waits for [pendingWork] after the ticks finished.
  final Duration maxPendingWait;

  /// Opens the store review sheet; defaults to `in_app_review`. Injectable for tests.
  final Future<void> Function()? requestReview;

  static const int stepCount = 5;

  @override
  State<OnboardingSetupPage> createState() => _OnboardingSetupPageState();
}

class _OnboardingSetupPageState extends State<OnboardingSetupPage> with SingleTickerProviderStateMixin {
  late final AnimationController _entrance;
  final List<Timer> _timers = [];
  int _completed = 0;
  bool _finished = false;
  bool _promptOpen = false;
  bool _promptShown = false;
  Completer<void>? _promptClosed;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(vsync: this, duration: const Duration(milliseconds: 500))..forward();
    for (var i = 1; i <= OnboardingSetupPage.stepCount; i++) {
      _timers.add(Timer(widget.stepInterval * i, () => _tick(i)));
    }
    _timers.add(Timer(widget.ratingPromptDelay, _showRatingPrompt));
  }

  @override
  void dispose() {
    for (final timer in _timers) {
      timer.cancel();
    }
    _entrance.dispose();
    super.dispose();
  }

  void _tick(int completed) {
    if (!mounted) return;
    setState(() => _completed = completed);
    OmiHaptics.selection();
    if (completed == OnboardingSetupPage.stepCount) unawaited(_finishWhenReady());
  }

  Future<void> _finishWhenReady() async {
    final work = widget.pendingWork;
    if (work != null) {
      // Real setup may still be running; wait for it, but never longer than the cap.
      await work.timeout(widget.maxPendingWait, onTimeout: () {}).catchError((_) {});
    }
    // Let the last tick land before leaving; the alert, if open, holds the page.
    await Future<void>.delayed(const Duration(milliseconds: 450));
    if (_promptOpen) await _promptClosed!.future;
    if (!mounted || _finished) return;
    _finished = true;
    widget.onFinished();
  }

  Future<void> _showRatingPrompt() async {
    if (!mounted || _promptShown) return;
    _promptShown = true;
    _promptOpen = true;
    _promptClosed = Completer<void>();
    const TypedEvents().emit(const OnboardingSetupRatingPromptShown());
    final l10n = context.l10n;
    final native = nativePresentationEnabled
        ? await showIosNativeModal(context,
            title: l10n.onboardingRatingPromptTitle,
            alert: true,
            dismissible: false,
            cancelId: 'not_really',
            actions: [
                NativeRow('not_really', l10n.onboardingRatingPromptNo),
                NativeRow('support', l10n.onboardingRatingPromptYes),
              ],
            sections: [
                NativeSection('rating', [NativeRow('rating_message', l10n.onboardingRatingPromptBody, kind: 'label')]),
              ])
        : null;
    final answer = native != null
        ? nativeRatingAnswer(native)
        : !mounted
            ? null
            : await showDialog<OnboardingSetupRatingPromptAnsweredAnswer>(
                context: context,
                barrierDismissible: false,
                builder: (dialogContext) => OmiAlertDialog(
                  title: l10n.onboardingRatingPromptTitle,
                  message: l10n.onboardingRatingPromptBody,
                  actions: [
                    OmiDialogAction(
                      key: const Key('onboarding_rating_yes'),
                      label: l10n.onboardingRatingPromptYes,
                      isDefault: true,
                      onPressed: () =>
                          Navigator.of(dialogContext).pop(OnboardingSetupRatingPromptAnsweredAnswer.support),
                    ),
                    OmiDialogAction(
                      key: const Key('onboarding_rating_no'),
                      label: l10n.onboardingRatingPromptNo,
                      onPressed: () =>
                          Navigator.of(dialogContext).pop(OnboardingSetupRatingPromptAnsweredAnswer.notReally),
                    ),
                  ],
                ),
              );
    _promptOpen = false;
    _promptClosed!.complete();
    if (answer == null) return;
    const TypedEvents().emit(OnboardingSetupRatingPromptAnswered(answer: answer));
    if (answer == OnboardingSetupRatingPromptAnsweredAnswer.support) {
      OmiHaptics.success();
      try {
        // The store decides whether its sheet appears (and never on the simulator).
        await (widget.requestReview ?? InAppReview.instance.requestReview)();
      } catch (error) {
        debugPrint('OnboardingSetupPage: review request failed: $error');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final classic = _buildClassic(context);
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final steps = _steps(context);
    return IosNativeSurface(
      title: l10n.onboardingSetupTitle,
      largeTitle: true,
      publicSurface: true,
      fallback: classic,
      sections: [
        NativeSection('onboarding_setup_intro', [
          NativeRow('onboarding_setup_subtitle', l10n.onboardingSetupSubtitle, kind: 'label'),
        ]),
        NativeSection('onboarding_setup_steps', [
          for (var i = 0; i < steps.length; i++)
            NativeRow('onboarding_setup_step_$i', steps[i],
                kind: 'label',
                symbol: i < _completed
                    ? 'checkmark.circle.fill'
                    : i == _completed
                        ? 'circle.dotted'
                        : 'circle'),
        ]),
      ],
    );
  }

  /// The one checklist source shared by the native and classic presentations.
  List<String> _steps(BuildContext context) {
    final l10n = context.l10n;
    final steps = [
      l10n.onboardingSetupStepWorkspace,
      l10n.onboardingSetupStepLanguage,
      l10n.onboardingSetupStepMemory,
      l10n.onboardingSetupStepDevices,
      l10n.onboardingSetupStepPersonalize,
    ];
    assert(steps.length == OnboardingSetupPage.stepCount);
    return steps;
  }

  Widget _buildClassic(BuildContext context) {
    final l10n = context.l10n;
    final steps = _steps(context);
    return Container(
      key: const Key('onboarding_setup_page'),
      color: OmiColors.surface0,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: FadeTransition(
          opacity: CurvedAnimation(parent: _entrance, curve: Curves.easeOut),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl),
            child: LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: constraints.maxHeight),
                  child: IntrinsicHeight(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Spacer(flex: 2),
                        Semantics(
                          header: true,
                          child: Text(l10n.onboardingSetupTitle, style: OmiType.title1.copyWith(height: 1.2)),
                        ),
                        const SizedBox(height: OmiSpacing.xs),
                        Text(
                          l10n.onboardingSetupSubtitle,
                          style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.4),
                        ),
                        const SizedBox(height: OmiSpacing.xxl + OmiSpacing.md),
                        for (var i = 0; i < steps.length; i++)
                          _SetupStepRow(
                            key: Key('onboarding_setup_step_$i'),
                            label: steps[i],
                            state: i < _completed
                                ? _StepState.done
                                : i == _completed
                                    ? _StepState.active
                                    : _StepState.pending,
                          ),
                        const Spacer(flex: 3),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// How the native rating alert was answered: Yes is support, the Not Really (cancel) action is
/// notReally, and anything else (an invalidated session, an unmounted page, a dismissal) is no answer.
@visibleForTesting
OnboardingSetupRatingPromptAnsweredAnswer? nativeRatingAnswer(NativeModalResult result) {
  if (result.action == 'support') return OnboardingSetupRatingPromptAnsweredAnswer.support;
  if (result.reason == 'cancel') return OnboardingSetupRatingPromptAnsweredAnswer.notReally;
  return null;
}

enum _StepState { pending, active, done }

class _SetupStepRow extends StatelessWidget {
  const _SetupStepRow({super.key, required this.label, required this.state});

  final String label;
  final _StepState state;

  static const double _indicator = 26;

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    final done = state == _StepState.done;
    final textColor = state == _StepState.pending ? OmiColors.textTertiary : OmiColors.textPrimary;
    return Semantics(
      checked: done,
      label: label,
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
        child: Row(
          children: [
            SizedBox.square(
              dimension: _indicator,
              child: AnimatedSwitcher(
                duration: motion.standard,
                switchInCurve: Curves.easeOutBack,
                switchOutCurve: Curves.easeIn,
                transitionBuilder: (child, animation) => ScaleTransition(
                  scale: animation,
                  child: FadeTransition(opacity: animation, child: child),
                ),
                child: switch (state) {
                  _StepState.done => Container(
                      key: const ValueKey('done'),
                      decoration: BoxDecoration(color: OmiColors.textPrimary, shape: BoxShape.circle),
                      child: Icon(Icons.check_rounded, size: 16, color: OmiColors.onAccent),
                    ),
                  _StepState.active => Padding(
                      key: const ValueKey('active'),
                      padding: const EdgeInsets.all(1),
                      child: OmiSpinner(size: OmiSpinnerSize.regular, color: OmiColors.textPrimary),
                    ),
                  _StepState.pending => Container(
                      key: const ValueKey('pending'),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: OmiColors.border, width: 1.5),
                      ),
                    ),
                },
              ),
            ),
            const SizedBox(width: OmiSpacing.md),
            Expanded(
              child: AnimatedDefaultTextStyle(
                duration: motion.standard,
                curve: OmiMotion.standardCurve,
                style: OmiType.body.copyWith(color: textColor, height: 1.3),
                child: Text(label),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
