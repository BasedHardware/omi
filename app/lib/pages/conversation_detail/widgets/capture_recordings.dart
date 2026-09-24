import 'package:flutter/material.dart';

import 'package:omi/pages/conversation_detail/capture_group_separation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// "1:57 PM – 2:59 PM", or the start alone when the recording has no end.
String? captureRecordingTimeWindow(BuildContext context, CaptureRecording recording) {
  final start = recording.startedAt;
  if (start == null) return null;
  final dates = OmiDateFormat.of(context);
  final end = recording.finishedAt;
  if (end == null || !end.isAfter(start)) return dates.time(start);
  return dates.timeRange(start, end);
}

/// "Desktop · 1:57 PM – 2:59 PM": the name a confirmation uses for one recording.
String captureRecordingLabel(BuildContext context, CaptureRecording recording) {
  final source = CaptureSources.label(context, recording.source);
  final window = captureRecordingTimeWindow(context, recording);
  return window == null ? source : '$source · $window';
}

/// The end of the header's facts for an event several devices recorded: the
/// devices as a small overlapping stack plus a count. Opens the recordings sheet.
class CaptureRecordingsChip extends StatelessWidget {
  const CaptureRecordingsChip({super.key, required this.recordings, required this.onTap});

  final List<CaptureRecording> recordings;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final count = context.l10n.captureRecordingsCount(recordings.length);
    return Semantics(
      button: true,
      label: count,
      excludeSemantics: true,
      child: GestureDetector(
        key: const Key('conversation_detail_recordings'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          OmiHaptics.selection();
          onTap();
        },
        child: Container(
          constraints: const BoxConstraints(minHeight: 30),
          padding: const EdgeInsets.only(left: 4, right: 8),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              CaptureSourceStack(sources: recordings.map((recording) => recording.source).toList()),
              const SizedBox(width: 6),
              Text(
                count,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
              ),
              const SizedBox(width: 2),
              const Icon(Icons.keyboard_arrow_down, size: 16, color: OmiColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}

/// Lists each recording of the event: device, time range, the open one checked.
/// A row opens its recording; "Separate…" splits it out after a confirmation.
Future<void> showCaptureRecordingsSheet(
  BuildContext context, {
  required List<CaptureRecording> recordings,
  required CaptureGroupSeparationController controller,
  required void Function(CaptureRecording recording) onOpen,
  required Future<bool> Function(CaptureRecording recording) onSeparate,
}) {
  controller.reset();
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.captureRecordingsSheetTitle,
    padding: EdgeInsets.zero,
    builder: (sheetContext) => CaptureRecordingsSheet(
      recordings: recordings,
      controller: controller,
      onOpen: (recording) {
        Navigator.pop(sheetContext);
        onOpen(recording);
      },
      onSeparate: (recording) async {
        if (!await confirmCaptureRecordingSeparation(sheetContext, recording)) return;
        final separated = await onSeparate(recording);
        // The page reloads behind the sheet; close it once the new membership is in.
        if (separated && sheetContext.mounted) Navigator.pop(sheetContext);
      },
    ),
  );
}

/// "Separate this recording?" — separation is sticky on the server, so it always asks.
Future<bool> confirmCaptureRecordingSeparation(BuildContext context, CaptureRecording recording) {
  return showOmiConfirm(
    context,
    title: context.l10n.captureRecordingSeparateTitle,
    message: context.l10n.captureRecordingSeparateMessage(captureRecordingLabel(context, recording)),
    confirmLabel: context.l10n.captureRecordingSeparateConfirm,
  );
}

class CaptureRecordingsSheet extends StatelessWidget {
  const CaptureRecordingsSheet({
    super.key,
    required this.recordings,
    required this.controller,
    required this.onOpen,
    required this.onSeparate,
  });

  final List<CaptureRecording> recordings;
  final CaptureGroupSeparationController controller;
  final void Function(CaptureRecording recording) onOpen;
  final void Function(CaptureRecording recording) onSeparate;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final (index, recording) in recordings.indexed) ...[
                if (index > 0) const Divider(height: 1, indent: 56, color: OmiColors.border),
                _row(context, recording),
              ],
              if (controller.phase == CaptureGroupSeparationPhase.failed)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, size: 16, color: OmiColors.warning),
                      const SizedBox(width: 6),
                      Text(
                        context.l10n.captureRecordingSeparateFailed,
                        style: OmiType.footnote.copyWith(color: OmiColors.warning),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 12),
            ],
          );
        },
      ),
    );
  }

  Widget _row(BuildContext context, CaptureRecording recording) {
    final isSeparating = controller.isBusy && controller.recordingId == recording.id;
    final window = captureRecordingTimeWindow(context, recording);
    return Row(
      children: [
        Expanded(
          child: Semantics(
            button: !recording.isCurrent,
            selected: recording.isCurrent,
            label: captureRecordingLabel(context, recording),
            excludeSemantics: true,
            child: InkWell(
              key: Key('conversation_detail_recording_${recording.id}'),
              onTap: recording.isCurrent || controller.isBusy ? null : () => onOpen(recording),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 8, 12),
                child: Row(
                  children: [
                    SizedBox(
                      width: 24,
                      child: isSeparating
                          ? const OmiSpinner(size: OmiSpinnerSize.small)
                          : Icon(CaptureSources.icon(recording.source), size: 20, color: OmiColors.textTertiary),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            CaptureSources.label(context, recording.source),
                            style: OmiType.callout.copyWith(
                              fontWeight: recording.isCurrent ? FontWeight.w600 : FontWeight.w500,
                            ),
                          ),
                          if (window != null)
                            Text(
                              window,
                              style: OmiType.footnote.copyWith(
                                color: OmiColors.textTertiary,
                                fontFeatures: const [FontFeature.tabularFigures()],
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (recording.isCurrent)
                      Semantics(
                        label: context.l10n.captureRecordingViewing,
                        child: const Icon(Icons.check, size: 18, color: OmiColors.textPrimary),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: OmiButton.tertiary(
            key: Key('conversation_detail_recording_separate_${recording.id}'),
            label: context.l10n.captureRecordingSeparate,
            size: OmiButtonSize.compact,
            onPressed: controller.isBusy ? null : () => onSeparate(recording),
          ),
        ),
      ],
    );
  }
}
