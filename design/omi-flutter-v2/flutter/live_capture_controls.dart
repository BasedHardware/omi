// Reference for the Home live capture card controls (design: Main.png).
// Two equal-width capsules: [Pause | Resume] (secondary) and [End] (primary).
// Wire them to the ONE capture API on main (#18839): pauseCapture / resumeCapture / finishCapture.
// "End" ends the current conversation; the device keeps listening for the next one.
//
// Target file on main: app/lib/pages/conversations/widgets/live_capture_card.dart
// Build it with the shared OmiButton if its API allows an icon + expanded width; otherwise this shape.
// Labels must come from l10n (UX contract) — the English strings here are placeholders.

import 'package:flutter/material.dart';

class LiveCaptureControls extends StatelessWidget {
  const LiveCaptureControls({
    super.key,
    required this.isPaused,
    required this.canPause, // photo-only devices have no pause (#18843)
    required this.onPause,
    required this.onResume,
    required this.onEnd,
    required this.pauseLabel, // l10n: "Pause"
    required this.resumeLabel, // l10n: "Resume"
    required this.endLabel, // l10n: "End"
    required this.surface, // OmiColors.surface2
    required this.textColor, // OmiColors.textPrimary
    required this.accent, // OmiColors.accent
    required this.onAccent, // OmiColors.onAccent
    required this.labelStyle, // OmiType.subhead.copyWith(fontWeight: FontWeight.w600)
  });

  final bool isPaused;
  final bool canPause;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onEnd;
  final String pauseLabel;
  final String resumeLabel;
  final String endLabel;
  final Color surface;
  final Color textColor;
  final Color accent;
  final Color onAccent;
  final TextStyle labelStyle;

  @override
  Widget build(BuildContext context) {
    Widget capsule({required Widget icon, required String label, required Color bg, required Color fg, required VoidCallback onTap}) {
      return Expanded(
        child: Semantics(
          button: true,
          label: label,
          child: Material(
            color: bg,
            shape: const StadiumBorder(),
            child: InkWell(
              customBorder: const StadiumBorder(),
              onTap: onTap,
              child: SizedBox(
                height: 46, // >= 44 pt target
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  IconTheme(data: IconThemeData(color: fg, size: 15), child: icon),
                  const SizedBox(width: 8),
                  Text(label, style: labelStyle.copyWith(color: fg)),
                ]),
              ),
            ),
          ),
        ),
      );
    }

    return Row(children: [
      if (canPause) ...[
        capsule(
          icon: Icon(isPaused ? Icons.play_arrow_rounded : Icons.pause_rounded),
          label: isPaused ? resumeLabel : pauseLabel,
          bg: surface,
          fg: textColor,
          onTap: isPaused ? onResume : onPause,
        ),
        const SizedBox(width: 10),
      ],
      capsule(icon: const Icon(Icons.stop_rounded), label: endLabel, bg: accent, fg: onAccent, onTap: onEnd),
    ]);
  }
}
