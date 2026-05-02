import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/library/conversation_detail_screen.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/library/widgets/conversation_row.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Meetings sub-tab — list of conversations the assistant has captured,
/// grouped by date bucket. Tap pushes [ConversationDetailScreen].
class ConversationsView extends StatefulWidget {
  const ConversationsView({super.key, this.scrollToConversationId});

  /// When set, on first build we scroll the matching row into view. The
  /// shell sets this when the user came in from a memory's "View
  /// conversation" affordance and clears it once consumed.
  final String? scrollToConversationId;

  @override
  State<ConversationsView> createState() => _ConversationsViewState();
}

class _ConversationsViewState extends State<ConversationsView> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ConversationsProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ConversationsProvider>();

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
        // Scaffold sets MediaQuery.padding.top = AppBar.preferredSize.height
        // when extendBodyBehindAppBar is true — that already covers the
        // status bar, the toolbar, AND our section pill bar in `bottom:`.
        // Just add a small breathing gap.
        padding: EdgeInsets.fromLTRB(
          AppStyles.spacingL,
          MediaQuery.of(context).padding.top + AppStyles.spacingS,
          AppStyles.spacingL,
          AppStyles.spacingXL,
        ),
        itemCount: groups.length,
        itemBuilder: (_, i) {
          final g = groups[i];
          return Padding(
            padding: const EdgeInsets.only(bottom: AppStyles.spacingL),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS),
                  child: Text(
                    g.label.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textTertiary,
                      letterSpacing: 0.8,
                    ),
                  ),
                ),
                const SizedBox(height: AppStyles.spacingS),
                for (final c in g.items)
                  ConversationRow(
                    key: ValueKey(c.id),
                    item: c,
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ConversationDetailScreen(item: c),
                        ),
                      );
                    },
                  ),
              ],
            ),
          );
        },
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
            "No conversations yet. Start chatting and Nooto will save them here.",
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
              "Couldn't load your conversations.",
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
