import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// Motion N3: the live card's orb flies into the Live page's (the card grows into the page).
const String kLiveOrbHeroTag = 'omi-live-orb';

/// The one capture status and control surface on Home: what is recording now (v2 `Main`).
///
/// Row 1 is the state in words ("Listening") behind a status dot, and the elapsed time. Row 2
/// names the source. Then the latest transcript, and two equal capsules: Pause or Resume, and
/// Finish, which ends and processes this conversation (the device keeps listening for the next).
/// The dot is [OmiColors.live] only while audio is really being captured; paused or degraded is
/// [OmiColors.warning]. A call shows a chevron instead of controls: the call page owns them.
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
    this.onFinish,
  });

  /// A conversation source ('omi', 'phone', …) or [callSource].
  final String source;
  final String stateLabel;

  /// Paused or degraded (amber dot) rather than live (blue dot).
  final bool paused;
  final Duration? elapsed;
  final String? lastLine;
  final String? note;

  /// Null hides the Pause/Resume control.
  final VoidCallback? onPauseToggle;

  /// Null hides Finish.
  final VoidCallback? onFinish;

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

  /// The transcript's older words and its newest sentence, so the card can grey the one and
  /// keep the other bright ("…a quick update on the reports. Are they valid?").
  static (String, String) splitLatest(String line) {
    final text = line.trim();
    final breaks = RegExp(r'[.!?…]\s+');
    var cut = -1;
    for (final match in breaks.allMatches(text)) {
      if (match.end < text.length) cut = match.end;
    }
    if (cut <= 0) return ('', text);
    return (text.substring(0, cut).trimRight(), text.substring(cut));
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
    // Liquid Dock: the orb (its LED breathes while audio is captured) for a wearable; the source's
    // own mark in a circle for the phone or a call.
    final Widget thumb = !isCall && source != 'phone'
        ? Hero(tag: kLiveOrbHeroTag, child: OmiOrb(size: 44, live: !paused))
        : Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
            child: Stack(
              alignment: Alignment.center,
              children: [
                Icon(isCall ? Icons.call_rounded : CaptureSources.icon(source), size: 20, color: OmiColors.textPrimary),
                Positioned(
                  right: 4,
                  top: 4,
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: paused ? OmiColors.warning : OmiColors.live,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ],
            ),
          );
    final statusRow = Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        ExcludeSemantics(child: thumb),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Long states (offline buffering, in a long language) take a second line.
              Text(stateLabel, maxLines: 2, overflow: TextOverflow.ellipsis, style: OmiType.headline),
              Text(label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
        if (elapsed != null) ...[
          const SizedBox(width: OmiSpacing.xs),
          Text(
            formatElapsed(elapsed!),
            style: OmiType.title3.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
          ),
        ],
        const SizedBox(width: OmiSpacing.xs),
        OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
      ],
    );
    final showControls = !isCall && (onPauseToggle != null || onFinish != null);
    final line = lastLine?.trim() ?? '';
    final (older, latest) = splitLatest(line);
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      statusRow,
      // The listening wave: ripples while audio is captured, still and dim while paused.
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: OmiListeningWave(key: const Key('live_capture_wave'), live: !paused),
      ),
      if (line.isNotEmpty)
        Text.rich(
          TextSpan(children: [
            TextSpan(
              text: older.isEmpty ? '… ' : '…$older ',
              style: TextStyle(color: OmiColors.textTertiary),
            ),
            TextSpan(text: latest),
          ]),
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
          style: OmiType.callout,
        ),
      if (note != null) ...[
        const SizedBox(height: OmiSpacing.sm),
        Row(children: [
          Icon(CaptureSources.icon('omi'), size: 14, color: OmiColors.textTertiary),
          const SizedBox(width: OmiSpacing.xs),
          Flexible(child: Text(note!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary))),
        ]),
      ],
      if (showControls) ...[
        const SizedBox(height: OmiSpacing.md),
        Row(children: [
          if (onPauseToggle != null)
            Expanded(
              child: LiveCaptureAction(
                key: const Key('live_capture_pause'),
                label: paused ? l10n.resume : l10n.pause,
                icon: paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
                primary: false,
                onPressed: onPauseToggle!,
              ),
            ),
          if (onPauseToggle != null && onFinish != null) const SizedBox(width: 10),
          if (onFinish != null)
            Expanded(
              child: LiveCaptureAction(
                key: const Key('live_capture_finish'),
                label: l10n.endCapture,
                icon: Icons.stop_rounded,
                primary: true,
                onPressed: onFinish!,
              ),
            ),
        ]),
      ],
    ]);
  }
}

/// A live-card capsule (Liquid Dock `.cap`): 48 pt, 17 pt semibold. Pause on the fill; End white
/// with ink and a soft shadow. Dips when pressed.
/// One of the live card's two 48 pt capsules: [primary] is the accent (End, Start listening), the
/// other the quiet fill (Pause, Add a device).
class LiveCaptureAction extends StatelessWidget {
  const LiveCaptureAction({
    super.key,
    required this.label,
    required this.icon,
    required this.primary,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final bool primary;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final fg = primary ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      onTap: onPressed,
      child: OmiPressable(
        onTap: onPressed,
        child: Container(
          height: 48,
          decoration: BoxDecoration(
            color: primary ? OmiColors.accent : OmiColors.surface3,
            borderRadius: OmiRadius.pillAll,
            boxShadow:
                primary ? [BoxShadow(color: OmiColors.shadowSoft, blurRadius: 8, offset: const Offset(0, 2))] : null,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 16, color: fg),
              const SizedBox(width: OmiSpacing.xs),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.headline.copyWith(color: fg),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
