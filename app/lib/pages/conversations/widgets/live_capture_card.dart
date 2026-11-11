import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// The one capture status and control surface on Home: what is recording now.
///
/// The listening pill ([compact]) is one line: a small source glyph, a live dot, the short
/// [status], and the latest words. It does not show how long the pendant has been connected —
/// that clock is not the conversation. A problem ([explanation] set) turns the dot and the status
/// amber and replaces the preview with [detail]; tapping that text opens a sheet that explains it.
/// Trailing: Pause while live, Resume only when [paused]. A [note] sits under the line only when set.
///
/// Calls and Transcribe Later keep the stacked card: a source circle, the status, and the elapsed
/// time of *that* recording (the call, or audio saved so far), because those clocks are the thing
/// on screen.
class LiveCaptureCard extends StatelessWidget {
  const LiveCaptureCard({
    super.key,
    required this.source,
    required this.status,
    this.detail,
    this.explanation,
    this.paused = false,
    this.compact = false,
    this.elapsed,
    this.lastLine,
    this.note,
    this.onPauseToggle,
  });

  /// A conversation source ('omi', 'phone', …) or [callSource].
  final String source;

  /// Line 1: the short state name. Must fit one line at 320pt and 1.3x text in English.
  final String status;

  /// Line 2, after the timer: the consequence of the state, if any.
  final String? detail;

  /// For a problem state: what the details sheet says. Marks the card with a warning glyph.
  final String? explanation;

  /// The reader (or the pendant) paused capture: the trailing control resumes.
  final bool paused;

  /// One-line listening pill. Ignores [elapsed]: the session clock is not shown.
  final bool compact;
  final Duration? elapsed;
  final String? lastLine;
  final String? note;

  /// Null hides the Pause/Resume control.
  final VoidCallback? onPauseToggle;

  static const String callSource = 'call';

  /// Diameter of the leading source glyph's circle.
  static const double sourceDiameter = 36;

  /// The pill row's fixed width before the status: the source glyph, the live dot, and the two
  /// gaps around them.
  static const double _pillFixedBeforeStatus = 16 + 8 + 8 + 8;

  /// What the rest of the row needs after the status: the gap to the preview, the gap to the
  /// control, and the widest trailing control (the 44pt Pause target; the call chevron and the
  /// no-control cases are narrower, so reserving this much is always safe).
  static const double _pillReservedAfterStatus = 8 + 8 + kOmiMinTapTarget;

  /// Pausing means nothing to a photo-capture device (OmiGlass, Ray-Ban Meta): it keeps taking
  /// photos. The live card and the live page use this one rule.
  static bool canPause(BtDevice? device, {required String? source}) {
    if (source == null || source == 'phone') return true;
    final type = device?.type;
    return type != DeviceType.openglass && type != DeviceType.raybanMeta;
  }

  static String formatElapsed(Duration d) {
    final h = d.inHours, m = d.inMinutes % 60, s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return h > 0 ? '$h:${m.toString().padLeft(2, '0')}:$s' : '$m:$s';
  }

  /// The details sheet for a problem state: what is happening and that the audio is safe.
  static Future<void> showDetails(BuildContext context, {required String title, required String explanation}) {
    return showOmiSheet<void>(
      context: context,
      title: title,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.only(bottom: OmiSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(explanation, style: OmiType.body.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.lg),
            OmiButton(label: sheetContext.l10n.gotIt, onPressed: () => Navigator.pop(sheetContext)),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (compact) return _buildPill(context);
    return _buildStacked(context);
  }

  /// One line: glyph, live dot, status, the latest words, Pause. A problem replaces the words
  /// with [detail] and turns the dot and the status amber.
  Widget _buildPill(BuildContext context) {
    final l10n = context.l10n;
    final problem = explanation != null;
    final isCall = source == callSource;
    final preview = problem
        ? (detail?.trim().isNotEmpty == true ? detail!.trim() : null)
        : (lastLine?.trim().isNotEmpty == true ? lastLine!.trim() : null);
    final statusColor = problem ? OmiColors.warning : OmiColors.textPrimary;
    final dotColor = problem ? OmiColors.warning : (paused ? OmiColors.textTertiary : OmiColors.danger);
    final sourceName = isCall
        ? l10n.captureSourceCall
        : source == 'phone'
            ? l10n.phone
            : CaptureSources.label(context, source);

    Widget statusText = Text(
      status,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600, color: statusColor),
    );
    if (problem) {
      statusText = Semantics(
        button: true,
        hint: l10n.learnMore,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => showDetails(context, title: status, explanation: explanation!),
          child: statusText,
        ),
      );
    }

    return Container(
      // The pause control is a 44pt target around a 36pt circle. 2pt of pill padding leaves a
      // 48pt row, with the circle inset 6pt — the same inset as the approved pill.
      padding: const EdgeInsets.fromLTRB(12, 2, 2, 2),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        // A pill, not a card corner. OmiRadius has no capsule token.
        borderRadius: BorderRadius.circular(999), // omi-ux-allow: radius-literal -- capsule, not a card corner
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Short in English. The status keeps its natural width when it fits and gives up its
          // tail when it does not — never the pause. A plain Flexible would split the row evenly
          // (starving an English status that fits) and strand the control away from the trailing
          // edge on wide screens, so cap it by what is left after the glyphs, the gaps, and the
          // control. The cap is measured here, outside the Row: a Row sizes its non-flex children
          // without a main-axis bound, so a LayoutBuilder inside it would see infinity.
          LayoutBuilder(builder: (context, constraints) {
            final statusMax =
                (constraints.maxWidth - _pillFixedBeforeStatus - _pillReservedAfterStatus).clamp(0.0, 168.0);
            return Row(
              children: [
                Semantics(
                  label: sourceName,
                  excludeSemantics: true,
                  child: Icon(CaptureSources.icon(source), size: 16, color: OmiColors.textPrimary),
                ),
                const SizedBox(width: 8),
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
                ConstrainedBox(constraints: BoxConstraints(maxWidth: statusMax), child: statusText),
                if (preview != null) ...[
                  const SizedBox(width: 8),
                  Expanded(child: _pillPreview(context, preview, problem)),
                ] else
                  const Spacer(),
                if (isCall)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary),
                  )
                else if (onPauseToggle != null) ...[
                  const SizedBox(width: 8),
                  OmiIconButton.filled(
                    icon: Icon(paused ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 22),
                    label: paused ? l10n.resume : l10n.pause,
                    diameter: 36,
                    fillColor: OmiColors.surface3,
                    onPressed: onPauseToggle,
                  ),
                ],
              ],
            );
          }),
          if (note != null) ...[
            const SizedBox(height: 4),
            Text(
              note!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
            ),
          ],
        ],
      ),
    );
  }

  Widget _pillPreview(BuildContext context, String preview, bool problem) {
    final text = Text(
      preview,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
    );
    if (!problem) return text;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => showDetails(context, title: status, explanation: explanation!),
      child: text,
    );
  }

  Widget _buildStacked(BuildContext context) {
    final l10n = context.l10n;
    final isCall = source == callSource;
    final sourceName = isCall
        ? l10n.captureSourceCall
        : source == 'phone'
            ? l10n.phone
            : CaptureSources.label(context, source);
    final secondary = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    final problem = explanation != null;

    final leading = Semantics(
      label: sourceName,
      excludeSemantics: true,
      child: Container(
        width: sourceDiameter,
        height: sourceDiameter,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
        child: Icon(isCall ? Icons.call_rounded : CaptureSources.icon(source), size: 18, color: OmiColors.textPrimary),
      ),
    );

    final line2 = [
      if (elapsed != null) formatElapsed(elapsed!),
      if (detail != null) detail!,
    ].join('  ·  ');
    Widget text = Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        if (problem) ...[
          ExcludeSemantics(child: Icon(Icons.warning_amber_rounded, size: 18, color: OmiColors.warning)),
          const SizedBox(width: OmiSpacing.xxs),
        ],
        // The short status always fits in English; a longer translation gives up its tail only.
        Flexible(
          child: Text(status,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
        ),
      ]),
      if (line2.isNotEmpty)
        // The consequence wraps rather than losing its meaning at large text sizes.
        Text(line2,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: secondary.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
    ]);
    if (problem) {
      text = Semantics(
        button: true,
        hint: l10n.learnMore,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => showDetails(context, title: status, explanation: explanation!),
          child: ConstrainedBox(constraints: const BoxConstraints(minHeight: kOmiMinTapTarget), child: text),
        ),
      );
    }

    final statusRow = Row(children: [
      leading,
      const SizedBox(width: OmiSpacing.xs),
      Expanded(child: text),
      if (isCall)
        SizedBox(
          width: kOmiMinTapTarget,
          child: Icon(Icons.chevron_right_rounded, size: 22, color: OmiColors.textTertiary),
        )
      else if (onPauseToggle != null)
        OmiIconButton.filled(
          icon: Icon(paused ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 22),
          label: paused ? l10n.resume : l10n.pause,
          diameter: 36,
          fillColor: OmiColors.surface3,
          onPressed: onPauseToggle,
        ),
    ]);
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      statusRow,
      if (lastLine != null && lastLine!.trim().isNotEmpty) ...[
        const SizedBox(height: OmiSpacing.xs),
        Text('… ${lastLine!.trim()}', maxLines: 1, overflow: TextOverflow.ellipsis, style: secondary),
      ],
      if (note != null) ...[
        const SizedBox(height: OmiSpacing.sm),
        Row(children: [
          Icon(CaptureSources.icon('omi'), size: 14, color: OmiColors.textTertiary),
          const SizedBox(width: OmiSpacing.xs),
          Flexible(child: Text(note!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary))),
        ]),
      ],
    ]);
  }
}
