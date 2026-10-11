import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A quiet line above incomplete results: one kind failed to load; retry runs the search again.
class OmiPartialNotice extends StatelessWidget {
  const OmiPartialNotice({super.key, required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
        child: Row(
          children: [
            Icon(Icons.error_outline_rounded, size: 16, color: OmiColors.textTertiary),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(
              child: Text(l10n.searchPartialFailure, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ),
            OmiButton.secondary(
              key: const ValueKey('search_partial_retry'),
              label: l10n.tryAgain,
              size: OmiButtonSize.compact,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}
