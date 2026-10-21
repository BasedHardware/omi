import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Retryable placeholder shown when GET /v3/memories failed rather than
/// returning a genuine empty list.
class MemoriesLoadError extends StatelessWidget {
  final VoidCallback onRetry;

  const MemoriesLoadError({super.key, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    // OmiErrorState's shape, with the stable keys the journeys drive.
    return KeyedSubtree(
      key: const Key('memories_load_error'),
      child: OmiEmptyState(
        icon: Icons.error_outline,
        title: context.l10n.couldNotLoadMemories,
        action: OmiButton.secondary(
          key: const Key('memories_load_retry'),
          label: context.l10n.tryAgain,
          size: OmiButtonSize.compact,
          onPressed: onRetry,
        ),
      ),
    );
  }
}

/// Chooses the load-error placeholder over the empty-list placeholder.
class MemoriesEmptyOrError extends StatelessWidget {
  final bool showLoadError;
  final VoidCallback onRetry;
  final Widget emptyState;

  const MemoriesEmptyOrError({super.key, required this.showLoadError, required this.onRetry, required this.emptyState});

  @override
  Widget build(BuildContext context) {
    if (showLoadError) return MemoriesLoadError(onRetry: onRetry);
    return emptyState;
  }
}

/// Compact retry notice shown above retained rows when a later page of a
/// progressive load failed: the visible list is honest-but-incomplete, not a
/// silent success.
class MemoriesPartialLoadBanner extends StatelessWidget {
  final VoidCallback onRetry;

  const MemoriesPartialLoadBanner({super.key, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return KeyedSubtree(
      key: const Key('memories_partial_load_banner'),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
        child: Row(
          children: [
            Expanded(
              child: Text(
                context.l10n.couldNotLoadMemories,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            OmiButton.secondary(
              key: const Key('memories_partial_load_retry'),
              label: context.l10n.tryAgain,
              size: OmiButtonSize.compact,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}
