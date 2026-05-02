import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:nooto_v2/theme/app_theme.dart';

/// Tappable "Stop generating" pill rendered while the assistant message is
/// still streaming. Tapping fires a light haptic and invokes [onPressed],
/// which the chat screen wires to `ChatProvider.stopActiveStream()`. The
/// provider then marks the in-flight assistant message as `stopped: true`
/// so [StoppedMarker] renders inline below the partial text.
///
/// Sized to feel like a quiet inline affordance, not a primary CTA — the
/// surrounding bubble already carries the visual weight.
class StopStreamingButton extends StatelessWidget {
  const StopStreamingButton({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Stop generating response',
      child: InkWell(
        borderRadius: BorderRadius.circular(AppStyles.radiusPill),
        onTap: () {
          HapticFeedback.lightImpact();
          onPressed();
        },
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingM,
            vertical: 6,
          ),
          decoration: BoxDecoration(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(AppStyles.radiusPill),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.12),
              width: 0.5,
            ),
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.stop_rounded,
                size: 14,
                color: AppColors.brandPrimary,
              ),
              SizedBox(width: 6),
              Text(
                'Stop generating',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: AppColors.brandPrimary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Inline marker rendered below the partial assistant text on messages where
/// `message.stopped == true`. Quiet tertiary styling — it's a status
/// annotation, not an error. Pairs with the partial text already shown in
/// the bubble so the user can see how far the response got before they
/// stopped it.
class StoppedMarker extends StatelessWidget {
  const StoppedMarker({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Response was stopped by you',
      child: const Padding(
        padding: EdgeInsets.only(top: AppStyles.spacingS),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.stop_circle_outlined,
              size: 12,
              color: AppColors.textTertiary,
            ),
            SizedBox(width: 4),
            Text(
              'Stopped',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textTertiary,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
