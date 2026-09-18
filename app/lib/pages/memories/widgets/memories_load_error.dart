import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// Retryable placeholder shown when GET /v3/memories failed rather than
/// returning a genuine empty list.
class MemoriesLoadError extends StatelessWidget {
  final VoidCallback onRetry;

  const MemoriesLoadError({super.key, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        key: const Key('memories_load_error'),
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.error_outline, size: 48, color: Colors.grey.shade600),
          const SizedBox(height: 16),
          Text(
            context.l10n.couldNotLoadMemories,
            style: TextStyle(color: Colors.grey.shade400, fontSize: 18),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          TextButton(key: const Key('memories_load_retry'), onPressed: onRetry, child: Text(context.l10n.retry)),
        ],
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
