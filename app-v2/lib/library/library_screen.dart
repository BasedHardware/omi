import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/library/library_provider.dart';
import 'package:nooto_v2/library/memory_model.dart';
import 'package:nooto_v2/library/widgets/memory_row.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Tab 2: Library — Memory Map. What Nooto remembers about you, grouped
/// into 4 user-facing buckets, drilled into via inline expand. Read + delete
/// in v0; edit/search/manual-add land in v0.1.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
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
    final topInset = MediaQuery.of(context).padding.top + kToolbarHeight + AppStyles.spacingM;
    return RefreshIndicator(
      onRefresh: () => provider.load(force: true),
      color: AppColors.brandPrimary,
      backgroundColor: AppColors.backgroundSecondary,
      child: ListView.builder(
        padding: EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          topInset,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        itemCount: groups.length,
        itemBuilder: (_, i) => _GroupSection(group: groups[i]),
      ),
    );
  }
}

class _GroupSection extends StatelessWidget {
  const _GroupSection({required this.group});
  final MemoryGroup group;

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
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Conversation viewer lands in v0.1.'),
                    backgroundColor: AppColors.backgroundSecondary,
                  ),
                );
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
  Widget build(BuildContext context) {
    return const Center(
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
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
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
