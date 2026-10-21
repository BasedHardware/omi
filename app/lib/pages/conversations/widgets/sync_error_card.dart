import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Red banner shown on the sync page when a sync fails. The message must
/// reflow in full: it carries the recovery instruction (e.g. "press the
/// Pendant's button to stop recording, then sync again"), so it is never
/// clamped or ellipsized — a truncated error hides exactly what the user
/// needs to do, and truncation is worse at large accessibility text scales.
class SyncErrorCard extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const SyncErrorCard({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
      ),
      child: Row(
        // Top-align so the icon and Retry pill stay put when the message wraps
        // to several lines (long errors, or large accessibility text scales).
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.redAccent, size: 16),
          const SizedBox(width: 12),
          Expanded(
            // No maxLines/overflow: the message reflows in full.
            child: Text(
              message,
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: onRetry,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
              decoration: BoxDecoration(
                color: Colors.redAccent.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                context.l10n.retry,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontWeight: FontWeight.w500),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
