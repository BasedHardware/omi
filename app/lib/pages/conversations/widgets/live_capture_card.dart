import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// The one capture status and control surface on Home: what is recording now.
///
/// Leading: the source as a glyph in a circle (pendant, phone or call), named for screen readers
/// but not in text. Then two lines: the short [status] ("Listening", "Paused", "Not
/// transcribing"), and in a muted colour the elapsed time and the [detail] ("0:14 · Audio saved,
/// transcribes later"). A problem ([explanation] set) carries an amber warning glyph instead of a
/// status dot, and tapping the text opens a sheet that explains it. Trailing: Pause while live,
/// Resume only when [paused] (a pause glyph, since mics belong to Ask Omi); a call shows a chevron
/// because the call page owns the call's controls. Below: the latest transcript line and a [note].
class LiveCaptureCard extends StatelessWidget {
  const LiveCaptureCard({
    super.key,
    required this.source,
    required this.status,
    this.detail,
    this.explanation,
    this.paused = false,
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
  final Duration? elapsed;
  final String? lastLine;
  final String? note;

  /// Null hides the Pause/Resume control.
  final VoidCallback? onPauseToggle;

  static const String callSource = 'call';

  /// Diameter of the leading source glyph's circle.
  static const double sourceDiameter = 36;

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
        decoration: const BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
        child: Icon(isCall ? Icons.call_rounded : CaptureSources.icon(source), size: 18, color: OmiColors.textPrimary),
      ),
    );

    final line2 = [if (elapsed != null) formatElapsed(elapsed!), if (detail != null) detail!].join('  ·  ');
    Widget text = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (problem) ...[
              const ExcludeSemantics(child: Icon(Icons.warning_amber_rounded, size: 18, color: OmiColors.warning)),
              const SizedBox(width: OmiSpacing.xxs),
            ],
            // The short status always fits in English; a longer translation gives up its tail only.
            Flexible(
              child: Text(
                status,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        if (line2.isNotEmpty)
          // The consequence wraps rather than losing its meaning at large text sizes.
          Text(
            line2,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: secondary.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
          ),
      ],
    );
    if (problem) {
      text = Semantics(
        button: true,
        hint: l10n.learnMore,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => showDetails(context, title: status, explanation: explanation!),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
            child: text,
          ),
        ),
      );
    }

    final statusRow = Row(
      children: [
        leading,
        const SizedBox(width: OmiSpacing.xs),
        Expanded(child: text),
        if (isCall)
          const SizedBox(
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
      ],
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        statusRow,
        if (lastLine != null && lastLine!.trim().isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.sm),
          Text('… ${lastLine!.trim()}', maxLines: 1, overflow: TextOverflow.ellipsis, style: secondary),
        ],
        if (note != null) ...[
          const SizedBox(height: OmiSpacing.sm),
          Row(
            children: [
              Icon(CaptureSources.icon('omi'), size: 14, color: OmiColors.textTertiary),
              const SizedBox(width: OmiSpacing.xs),
              Flexible(
                child: Text(note!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
              ),
            ],
          ),
        ],
      ],
    );
  }
}
