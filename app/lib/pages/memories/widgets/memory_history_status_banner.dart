import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/ui_guidelines.dart';

/// Explains that the history projection is usable but incomplete.
///
/// This is intentionally informational: a truncated history response has no
/// resumable cursor, so the client must not invent a retry/continuation action.
class MemoryHistoryStatusBanner extends StatelessWidget {
  const MemoryHistoryStatusBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      excludeSemantics: true,
      liveRegion: true,
      label: context.l10n.memoryHistoryPartial,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
          border: Border.all(color: AppStyles.textTertiary.withValues(alpha: 0.35)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline, size: 18, color: AppStyles.textTertiary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                context.l10n.memoryHistoryPartial,
                style: TextStyle(color: AppStyles.textSecondary, fontSize: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
