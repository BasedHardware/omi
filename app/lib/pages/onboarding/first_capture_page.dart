import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'first_capture_controller.dart';

class FirstCapturePage extends StatelessWidget {
  const FirstCapturePage({super.key, required this.controller, required this.onComplete, required this.onSkip});
  final FirstCaptureController controller;
  final VoidCallback onComplete;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          final phase = controller.phase;
          final recording = phase == FirstCapturePhase.recording;
          final processing = phase == FirstCapturePhase.processing;
          final result = phase == FirstCapturePhase.result;
          final busy = phase == FirstCapturePhase.starting || processing;
          return Scaffold(
            backgroundColor: OmiColors.surface0,
            appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.firstCapturePhone)),
            body: SafeArea(
                child: ListView(padding: const EdgeInsets.all(OmiSpacing.lg), children: [
              const SizedBox(height: OmiSpacing.xl),
              Icon(result ? Icons.auto_awesome : Icons.mic_none, size: 56, color: OmiColors.textPrimary),
              const SizedBox(height: OmiSpacing.lg),
              Text(result ? context.l10n.firstCaptureResult : context.l10n.firstCapturePrompt,
                  style: result ? OmiType.title1 : OmiType.title2, textAlign: TextAlign.center),
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
                  ]),
                ),
              if (phase == FirstCapturePhase.empty ||
                  phase == FirstCapturePhase.error ||
                  phase == FirstCapturePhase.delayed)
                Semantics(
                    liveRegion: true,
                    child: Text(
                        phase == FirstCapturePhase.empty
                            ? context.l10n.firstCaptureEmpty
                            : phase == FirstCapturePhase.delayed
                                ? context.l10n.firstCaptureDelayed
                                : context.l10n.firstCaptureUnavailable,
                        key: const Key('first_capture_feedback'),
                        style: OmiType.body,
                        textAlign: TextAlign.center)),
              const SizedBox(height: OmiSpacing.xl),
              if (!processing)
                OmiButton(
                  labelStyle: OmiType.callout.copyWith(
                      fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
                  key: const Key('first_capture_primary'),
                  expand: true,
                  isLoading: busy,
                  label: result
                      ? context.l10n.startUsingOmi
                      : recording
                          ? context.l10n.firstCaptureFinish
                          : phase == FirstCapturePhase.ready
                              ? context.l10n.firstCaptureStart
                              : context.l10n.tryAgain,
                  onPressed: busy || (recording && !controller.canFinish)
                      ? null
                      : result
                          ? onComplete
                          : recording
                              ? controller.finish
                              : controller.start,
                ),
              if (!recording && !busy && !result)
                OmiButton(
                    variant: OmiButtonVariant.tertiary,
                    labelStyle: OmiType.callout.copyWith(
                        fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
                    key: const Key('first_capture_skip'),
                    label: context.l10n.firstCaptureSkip,
                    onPressed: onSkip),
            ])),
          );
        },
      );
}
