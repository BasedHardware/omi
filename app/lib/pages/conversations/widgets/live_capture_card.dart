import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/capture_sources.dart';

/// Motion N3: the live card's orb flies into the Live page's (the card grows into the page).
const String kLiveOrbHeroTag = 'omi-live-orb';

/// The one capture status and control surface on Home: what is recording now (v2 `Main`).
///
/// Row 1 is the short [status] ("Listening", "Muted", "Reconnecting…") over the source's name and
/// the consequence of the state ([detail]: "Audio saved, transcribes later"), and the elapsed time.
/// A problem ([explanation] set) carries an amber warning glyph, and tapping the text opens a sheet
/// that explains it. Then the listening wave, the latest transcript, and at most two equal capsules:
/// Mute (Unmute once the reader muted, [paused]) and Stop, which saves this conversation and stops
/// listening until Start. The orb's LED and the wave move only while audio is really being captured
/// ([live]). A call shows a chevron instead of controls: the call page owns them.
class LiveCaptureCard extends StatelessWidget {
  const LiveCaptureCard({
    super.key,
    required this.source,
    required this.status,
    this.detail,
    this.explanation,
    this.paused = false,
    bool? live,
    this.elapsed,
    this.lastLine,
    this.note,
    this.onPauseToggle,
    this.onFinish,
  }) : live = live ?? !paused;

  /// A conversation source ('omi', 'phone', …) or [callSource].
  final String source;

  /// The short state name. Must fit one line at 320pt and 1.3x text in English.
  final String status;

  /// After the source's name: the consequence of the state, if any.
  final String? detail;

  /// For a problem state: what the details sheet says. Marks the card with a warning glyph.
  final String? explanation;

  /// The reader (or the pendant's double tap) muted capture: the Mute capsule unmutes.
  final bool paused;

  /// Audio is being captured right now (the orb's LED, the moving wave). Defaults to not [paused].
  final bool live;
  final Duration? elapsed;
  final String? lastLine;
  final String? note;

  /// Null hides Mute/Unmute (glasses cannot mute).
  final VoidCallback? onPauseToggle;

  /// Null hides Stop.
  final VoidCallback? onFinish;

  static const String callSource = 'call';

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
    final problem = explanation != null;
    // Liquid Dock: the orb (its LED breathes while audio is captured) for a wearable; the source's
    // own mark in a circle for the phone or a call.
    final Widget thumb = !isCall && source != 'phone'
        ? Hero(tag: kLiveOrbHeroTag, child: OmiOrb(size: 44, live: live))
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
                      color: live ? OmiColors.live : OmiColors.warning,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ],
            ),
          );
    Widget text = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          if (problem) ...[
            ExcludeSemantics(child: Icon(Icons.warning_amber_rounded, size: 18, color: OmiColors.warning)),
            const SizedBox(width: OmiSpacing.xxs),
          ],
          // Long states (in a long language) take a second line.
          Flexible(child: Text(status, maxLines: 2, overflow: TextOverflow.ellipsis, style: OmiType.headline)),
        ]),
        // The consequence wraps rather than losing its meaning at large text sizes.
        Text(
          detail == null ? sourceName : '$sourceName · $detail',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
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
          child: ConstrainedBox(constraints: const BoxConstraints(minHeight: kOmiMinTapTarget), child: text),
        ),
      );
    }
    final statusRow = Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        ExcludeSemantics(child: thumb),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(child: text),
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
      // The listening wave: ripples while audio is captured, still and dim otherwise.
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: OmiListeningWave(key: const Key('live_capture_wave'), live: live),
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
                key: const Key('live_capture_mute'),
                label: paused ? l10n.unmute : l10n.mute,
                icon: paused ? Icons.mic_rounded : Icons.mic_off_rounded,
                primary: false,
                onPressed: onPauseToggle!,
              ),
            ),
          if (onPauseToggle != null && onFinish != null) const SizedBox(width: 10),
          if (onFinish != null)
            Expanded(
              child: LiveCaptureAction(
                key: const Key('live_capture_stop'),
                label: l10n.stop,
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

/// One of the live card's two 48 pt capsules (Liquid Dock `.cap`, 17 pt semibold): [primary] is the
/// accent (Stop, Start) with a soft shadow, the other the quiet fill (Mute, Manage devices).
/// Dips when pressed.
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
