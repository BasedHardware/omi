import 'dart:async';
import 'package:flutter/material.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'first_capture_controller.dart';
import 'first_capture_layout.dart';

class FirstCapturePage extends StatefulWidget {
  const FirstCapturePage(
      {super.key,
      required this.controller,
      required this.onComplete,
      required this.onSkip,
      this.showSiriHint,
      this.appShortcutsAvailabilityProbe});
  final FirstCaptureController controller;
  final VoidCallback onComplete;
  final VoidCallback onSkip;
  final bool? showSiriHint;
  final Future<bool> Function()? appShortcutsAvailabilityProbe;
  @override
  State<FirstCapturePage> createState() => _FirstCapturePageState();
}

class _FirstCapturePageState extends State<FirstCapturePage> {
  late final VoidCallback _releaseFeedback;
  bool _siriAvailable = false;
  bool _confirming = false;
  FirstCaptureController get controller => widget.controller;
  @override
  void initState() {
    super.initState();
    _releaseFeedback = OmiFeedback.ownInfoFeedback();
    if (widget.showSiriHint ?? PlatformService.isIOSAtLeast(16)) {
      unawaited(_loadSiri());
    }
  }

  Future<void> _loadSiri() async {
    try {
      final available =
          await (widget.appShortcutsAvailabilityProbe ?? SiriIntegration.instance.appShortcutsAvailable)();
      if (mounted) setState(() => _siriAvailable = available);
    } catch (_) {/* Keep the hint hidden if the native bridge is unavailable. */}
  }

  Future<void> _finish() async {
    if (_confirming) return;
    if (controller.seconds < 15) {
      _confirming = true;
      final bool confirmed;
      try {
        confirmed = await showOmiConfirm(context,
            title: context.l10n.firstCaptureShortTitle,
            message: context.l10n.firstCaptureShortWarning,
            confirmLabel: context.l10n.firstCaptureFinish,
            cancelLabel: context.l10n.keepRecording);
      } finally {
        _confirming = false;
      }
      if (!confirmed || !mounted) return;
    }
    await controller.finish();
  }

  Future<void> _back() async {
    if (_confirming) return;
    if (controller.phase == FirstCapturePhase.recording || controller.phase == FirstCapturePhase.starting) {
      _confirming = true;
      final confirmed = await showOmiConfirm(context,
          title: context.l10n.firstCaptureCancelTitle,
          message: context.l10n.firstCaptureCancelWarning,
          confirmLabel: context.l10n.stopRecording,
          cancelLabel: context.l10n.keepRecording,
          destructive: true);
      _confirming = false;
      if (!confirmed || !mounted) return;
    }
    await controller.leave();
    if (mounted) Navigator.of(context).pop();
  }

  @override
  void dispose() {
    _releaseFeedback();
    unawaited(controller.leave());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final phase = controller.phase;
        final recording = phase == FirstCapturePhase.recording;
        final processing = phase == FirstCapturePhase.processing;
        final result = phase == FirstCapturePhase.result;
        final empty = phase == FirstCapturePhase.empty;
        final busy = phase == FirstCapturePhase.starting || processing;
        final labelStyle = OmiType.callout
            .copyWith(fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily);
        return PopScope(
          canPop: !recording && phase != FirstCapturePhase.starting,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) unawaited(_back());
          },
          child: Scaffold(
              backgroundColor: OmiColors.surface0,
              appBar: AppBar(leading: OmiBackButton(onPressed: _back), title: Text(context.l10n.firstCapturePhone)),
              body: FirstCaptureLayout(content: [
                Icon(
                    result
                        ? Icons.auto_awesome
                        : empty
                            ? Icons.refresh
                            : Icons.mic_none,
                    size: 56,
                    color: OmiColors.textPrimary),
                const SizedBox(height: OmiSpacing.lg),
                Text(
                    empty
                        ? context.l10n.firstCaptureEmptyTitle
                        : result || processing || phase == FirstCapturePhase.delayed
                            ? context.l10n.firstCaptureResult
                            : context.l10n.firstCapturePrompt,
                    style: result || empty || processing || phase == FirstCapturePhase.delayed
                        ? OmiType.title1
                        : OmiType.title2,
                    textAlign: TextAlign.center),
                const SizedBox(height: OmiSpacing.xl),
                if (recording) ...[
                  Text(OmiDuration.offset(controller.seconds),
                      key: const Key('first_capture_timer'), style: OmiType.largeTitle, textAlign: TextAlign.center),
                  const SizedBox(height: OmiSpacing.sm),
                  LinearProgressIndicator(value: (controller.seconds / 30).clamp(0, 1)),
                  const SizedBox(height: OmiSpacing.md),
                  Text(controller.seconds < 30 ? context.l10n.firstCaptureKeepGoing : context.l10n.firstCaptureReady,
                      style: OmiType.body, textAlign: TextAlign.center),
                  const SizedBox(height: OmiSpacing.lg),
                  Semantics(
                      liveRegion: true,
                      child: Text(
                          controller.transcript.isEmpty ? context.l10n.firstCaptureListening : controller.transcript,
                          key: const Key('first_capture_transcript'),
                          style: OmiType.body)),
                ],
                if (processing) ...[
                  const Center(child: OmiSpinner()),
                  const SizedBox(height: OmiSpacing.md),
                  Text(context.l10n.firstCaptureProcessing, textAlign: TextAlign.center, style: OmiType.body),
                ],
                if (result)
                  Container(
                      key: const Key('first_capture_result_card'),
                      padding: const EdgeInsets.all(OmiSpacing.lg),
                      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(controller.conversation!.structured.title, style: OmiType.title2),
                        const SizedBox(height: OmiSpacing.md),
                        Text(controller.conversation!.structured.overview, style: OmiType.body),
                      ])),
                if (empty || phase == FirstCapturePhase.error || phase == FirstCapturePhase.delayed)
                  Semantics(
                      liveRegion: true,
                      child: Text(
                          empty
                              ? context.l10n.firstCaptureEmpty
                              : phase == FirstCapturePhase.delayed
                                  ? context.l10n.firstCaptureDelayed
                                  : context.l10n.firstCaptureUnavailable,
                          key: const Key('first_capture_feedback'),
                          style: OmiType.body,
                          textAlign: TextAlign.center)),
              ], actions: [
                if (result && _siriAvailable)
                  Padding(
                      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
                      child: Tooltip(
                          message: context.l10n.siriShortcutsSetupHint('Ask Omi', 'Question for Omi'),
                          child: Text(context.l10n.firstCaptureSiriTip,
                              key: const Key('onboarding_siri_hint'),
                              style: OmiType.footnote,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center))),
                if (!processing)
                  OmiButton(
                      key: const Key('first_capture_primary'),
                      labelStyle: labelStyle,
                      expand: true,
                      isLoading: busy,
                      label: result
                          ? context.l10n.startUsingOmi
                          : recording
                              ? context.l10n.firstCaptureFinish
                              : phase == FirstCapturePhase.ready
                                  ? context.l10n.firstCaptureStart
                                  : context.l10n.tryAgain,
                      onPressed: busy
                          ? null
                          : result
                              ? widget.onComplete
                              : recording
                                  ? () {
                                      // Confirmation is a decision, not a pending capture operation.
                                      unawaited(_finish());
                                    }
                                  : controller.start),
                if (!recording && !busy && !result)
                  OmiButton(
                      variant: OmiButtonVariant.tertiary,
                      labelStyle: labelStyle,
                      key: const Key('first_capture_skip'),
                      label: context.l10n.firstCaptureSkip,
                      onPressed: widget.onSkip),
              ])),
        );
      });
}
