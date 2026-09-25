import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// The one capture status and control surface on Home: what is recording now.
///
/// Row 1 names the source with the Recordings-sheet icon, then "● state · elapsed", then Pause or
/// Resume (a pause glyph: mics belong to Ask Omi). Row 2 is the latest transcript line. A call
/// shows a chevron instead of Pause, because the call page owns the call's controls.
class LiveCaptureCard extends StatelessWidget {
  const LiveCaptureCard({
    super.key,
    required this.source,
    required this.stateLabel,
    required this.paused,
    this.elapsed,
    this.lastLine,
    this.note,
    this.onPauseToggle,
  });

  /// A conversation source ('omi', 'phone', …) or [callSource].
  final String source;
  final String stateLabel;

  /// Paused or degraded (amber dot) rather than live (red dot).
  final bool paused;
  final Duration? elapsed;
  final String? lastLine;
  final String? note;

  /// Null hides the Pause/Resume control.
  final VoidCallback? onPauseToggle;

  static const String callSource = 'call';

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

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isCall = source == callSource;
    final label = isCall
        ? l10n.captureSourceCall
        : source == 'phone'
            ? l10n.phone
            : CaptureSources.label(context, source);
    final secondary = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    final separator = Text('  ·  ', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary));
    final statusRow = Row(children: [
      Expanded(
        child: Row(children: [
          ExcludeSemantics(
            child:
                Icon(isCall ? Icons.call_rounded : CaptureSources.icon(source), size: 18, color: OmiColors.textPrimary),
          ),
          const SizedBox(width: OmiSpacing.xs),
          Text(label, maxLines: 1, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
          separator,
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: paused ? OmiColors.warning : OmiColors.danger, shape: BoxShape.circle),
          ),
          const SizedBox(width: OmiSpacing.xs),
          // The state gives way first on a narrow screen or in a long language.
          // Long states (offline buffering, in a long language) take a second line, not an ellipsis.
          Flexible(child: Text(stateLabel, maxLines: 2, overflow: TextOverflow.ellipsis, style: secondary)),
          if (elapsed != null) ...[
            separator,
            Text(formatElapsed(elapsed!),
                style: secondary.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
          ],
        ]),
      ),
      if (isCall)
        const Icon(Icons.chevron_right_rounded, size: 22, color: OmiColors.textTertiary)
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
