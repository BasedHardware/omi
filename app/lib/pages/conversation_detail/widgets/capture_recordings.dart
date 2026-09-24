import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:intl/intl.dart';

import 'package:omi/pages/conversation_detail/capture_group_separation.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// "1:57 PM – 2:59 PM", or the start alone when the recording has no end.
String? captureRecordingTimeWindow(BuildContext context, CaptureRecording recording) {
  final start = recording.startedAt;
  if (start == null) return null;
  final format = DateFormat.jm(Localizations.localeOf(context).toString());
  final end = recording.finishedAt;
  if (end == null || !end.isAfter(start)) return format.format(start);
  return '${format.format(start)} – ${format.format(end)}';
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
          HapticFeedback.selectionClick();
          onTap();
        },
        child: Container(
          height: 30,
          padding: const EdgeInsets.only(left: 4, right: 8),
          decoration:
              BoxDecoration(color: Colors.grey.withValues(alpha: 0.16), borderRadius: BorderRadius.circular(15)),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              CaptureSourceStack(sources: recordings.map((recording) => recording.source).toList()),
              const SizedBox(width: 6),
              Text(
                count,
                style: TextStyle(color: Colors.grey.shade300, fontSize: 13, fontWeight: FontWeight.w500),
              ),
              const SizedBox(width: 2),
              Icon(Icons.keyboard_arrow_down, size: 16, color: Colors.grey.shade300),
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
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: const Color(0xFF1C1C1E),
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (sheetContext) => CaptureRecordingsSheet(
      recordings: recordings,
      controller: controller,
      onOpen: (recording) {
        Navigator.pop(sheetContext);
        onOpen(recording);
      },
      onSeparate: (recording) async {
        final confirmed = await confirmCaptureRecordingSeparation(sheetContext, recording);
        if (confirmed != true) return;
        final separated = await onSeparate(recording);
        // The page reloads behind the sheet; close it once the new membership is in.
        if (separated && sheetContext.mounted) Navigator.pop(sheetContext);
      },
    ),
  );
}

Future<bool?> confirmCaptureRecordingSeparation(BuildContext context, CaptureRecording recording) {
  return showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: const Color(0xFF1C1C1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Text(context.l10n.captureRecordingSeparateTitle, style: const TextStyle(color: Colors.white)),
      content: Text(
        context.l10n.captureRecordingSeparateMessage(captureRecordingLabel(context, recording)),
        style: const TextStyle(color: Color(0xFF8E8E93)),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: Text(context.l10n.cancel, style: const TextStyle(color: Color(0xFF8E8E93))),
        ),
        TextButton(
          key: const Key('conversation_detail_recording_separate_confirm'),
          onPressed: () => Navigator.pop(dialogContext, true),
          child: Text(context.l10n.captureRecordingSeparateConfirm, style: const TextStyle(color: Colors.white)),
        ),
      ],
    ),
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
              Center(
                child: Container(
                  margin: const EdgeInsets.only(top: 8),
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Text(
                  context.l10n.captureRecordingsSheetTitle,
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 13, fontWeight: FontWeight.w600),
                ),
              ),
              for (final (index, recording) in recordings.indexed) ...[
                if (index > 0) Divider(height: 1, indent: 56, color: Colors.white.withValues(alpha: 0.08)),
                _row(context, recording),
              ],
              if (controller.phase == CaptureGroupSeparationPhase.failed)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, size: 16, color: Colors.orangeAccent),
                      const SizedBox(width: 6),
                      Text(
                        context.l10n.captureRecordingSeparateFailed,
                        style: const TextStyle(color: Colors.orangeAccent, fontSize: 13),
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
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                            )
                          : Icon(CaptureSources.icon(recording.source), size: 20, color: Colors.grey.shade400),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            CaptureSources.label(context, recording.source),
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: recording.isCurrent ? FontWeight.w600 : FontWeight.w500,
                            ),
                          ),
                          if (window != null)
                            Text(
                              window,
                              style: TextStyle(
                                color: Colors.grey.shade500,
                                fontSize: 13,
                                fontFeatures: const [FontFeature.tabularFigures()],
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (recording.isCurrent)
                      Semantics(
                        label: context.l10n.captureRecordingViewing,
                        child: const Icon(Icons.check, size: 18, color: Colors.white),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(right: 8),
          child: TextButton(
            key: Key('conversation_detail_recording_separate_${recording.id}'),
            onPressed: controller.isBusy ? null : () => onSeparate(recording),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade300,
              minimumSize: const Size(44, 44),
              padding: const EdgeInsets.symmetric(horizontal: 12),
            ),
            child: Text(context.l10n.captureRecordingSeparate, style: const TextStyle(fontSize: 14)),
          ),
        ),
      ],
    );
  }
}
