import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/library/library_provider.dart';
import 'package:nooto_v2/library/memory_model.dart';
import 'package:nooto_v2/library/widgets/memory_row.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Memories sub-tab — the original Memory Map content. Pure body widget; the
/// shell owns the AppBar inset and the section tab bar above it.
class MemoriesView extends StatefulWidget {
  const MemoriesView({super.key, required this.onViewConversation});

  /// Caller routes to the Meetings sub-tab with this conversation pre-selected.
  final void Function(String conversationId) onViewConversation;

  @override
  State<MemoriesView> createState() => _MemoriesViewState();
}

class _MemoriesViewState extends State<MemoriesView> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<LibraryProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<LibraryProvider>();

    if (provider.loading && !provider.hasFetched) return const _Loading();
    if (provider.error != null && provider.isEmpty) {
      return _ErrorState(onRetry: () => provider.load(force: true));
    }
    if (provider.isEmpty) return const _EmptyState();

    final groups = provider.groups;
    return RefreshIndicator(
      onRefresh: () => provider.load(force: true),
      color: AppColors.brandPrimary,
      backgroundColor: AppColors.backgroundSecondary,
      child: ListView.builder(
        // See conversations_view.dart — MediaQuery.padding.top already
        // covers status bar + AppBar + section pill bar.
        padding: EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          MediaQuery.of(context).padding.top + AppStyles.spacingS,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        itemCount: groups.length,
        itemBuilder: (_, i) => _GroupSection(
          group: groups[i],
          onViewConversation: widget.onViewConversation,
        ),
      ),
    );
  }
}

class _GroupSection extends StatelessWidget {
  const _GroupSection({required this.group, required this.onViewConversation});

  final MemoryGroup group;
  final void Function(String conversationId) onViewConversation;

  @override
  Widget build(BuildContext context) {
    final provider = context.read<LibraryProvider>();
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingXL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS),
            child: Text(
              group.bucket.label,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: AppStyles.spacingS),
          for (final item in group.items)
            MemoryRow(
              key: ValueKey(item.id),
              item: item,
              onDelete: () async {
                HapticFeedback.lightImpact();
                final ok = await provider.delete(item.id);
                if (!ok && context.mounted && provider.error != null) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text("Couldn't delete that memory. Try again."),
                      backgroundColor: AppColors.backgroundSecondary,
                    ),
                  );
                }
              },
              onViewConversation: () {
                final cid = item.conversationId;
                if (cid == null || cid.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('No source conversation for this memory.'),
                      backgroundColor: AppColors.backgroundSecondary,
                    ),
                  );
                  return;
                }
                onViewConversation(cid);
              },
            ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();
  @override
  Widget build(BuildContext context) => const Center(
        child: SizedBox(
          width: 28,
          height: 28,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppColors.brandPrimary,
          ),
        ),
      );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
          child: Text(
            "Nothing saved yet. As we talk, I'll surface what I learn here.",
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 16,
              color: AppColors.textTertiary,
              height: 1.5,
            ),
          ),
        ),
      );
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              "Couldn't load your memories.",
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: AppStyles.spacingS),
            const Text(
              'Pull to retry, or tap below.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 14,
                color: AppColors.textTertiary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: AppStyles.spacingL),
            TextButton(
              onPressed: onRetry,
              child: const Text(
                'Retry',
                style: TextStyle(color: AppColors.brandPrimary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
