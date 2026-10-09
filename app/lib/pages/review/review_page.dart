import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Review: the few questions only the user can answer. Omi tidies everything else on its own;
/// what it changed is behind the quiet Recent Changes link.
class ReviewPage extends StatefulWidget {
  const ReviewPage({super.key});

  @override
  State<ReviewPage> createState() => _ReviewPageState();
}

class _ReviewPageState extends State<ReviewPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ReviewProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<ReviewProvider>();
    final items = provider.items;
    final Widget body;
    if (items.isEmpty && provider.loading) {
      body = const OmiLoadingState();
    } else if (items.isEmpty && provider.loadFailed) {
      body = OmiErrorState(message: l10n.reviewLoadFailed, onRetry: provider.load);
    } else if (items.isEmpty) {
      body = OmiEmptyState(
        icon: Icons.check_circle_outline,
        title: l10n.reviewCaughtUpTitle,
        message: l10n.reviewCaughtUpBody,
        action: _RecentChangesLink(),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: provider.load,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: [
            for (final item in items)
              ReviewQuestionCard(
                key: ValueKey(item.itemId),
                item: item,
                margin: const EdgeInsets.only(bottom: OmiSpacing.sm),
              ),
            Center(child: _RecentChangesLink()),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(l10n.reviewTitle),
        actions: [
          if (items.isNotEmpty)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: OmiSpacing.md),
              child: Center(
                child: Text(
                  l10n.reviewRemaining(provider.remainingToday),
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ),
            ),
        ],
      ),
      body: body,
    );
  }
}

class _RecentChangesLink extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return OmiButton.tertiary(
      key: const Key('review_recent_changes'),
      label: context.l10n.reviewRecentChanges,
      onPressed: () => routeToPage(context, const RecentChangesPage()),
    );
  }
}
