import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The card shown on the sync pages when a sync fails: an outlined card like the rest of Settings,
/// the message in red beside an error tile, and Retry under it. The message must reflow in full: it carries
/// the recovery instruction (e.g. "press the Pendant's button to stop recording, then sync
/// again"), so it is never clamped or ellipsized — a truncated error hides exactly what the user
/// needs to do, and truncation is worse at large accessibility text scales.
class SyncErrorCard extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const SyncErrorCard({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return OmiGroupedCard(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      child: Row(
        // Top-align so the tile stays put when the message wraps to several lines (long errors, or
        // large accessibility text scales).
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          OmiSettingsIconTile.custom(child: OmiLineIcon(OmiLineGlyph.info, color: OmiColors.danger)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(
            child: Padding(
              // Centres a one-line message on the 44 pt tile.
              padding: const EdgeInsets.only(top: OmiSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // No maxLines/overflow: the message reflows in full, across the card's width
                  // (Retry sits under it, not beside it).
                  Text(message, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
                  const SizedBox(height: OmiSpacing.sm),
                  OmiButton.secondary(label: context.l10n.retry, size: OmiButtonSize.compact, onPressed: onRetry),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
