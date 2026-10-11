import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/dream.dart' as dream_api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/review/dream_report_page.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Review: the few questions only the user can answer. Omi tidies everything else on its own;
/// what it changed is behind the quiet Recent Changes link.
class ReviewPage extends StatefulWidget {
  const ReviewPage({super.key, this.probeDreamReport});

  /// Decides whether the Dream Report link shows; defaults to a one-row fetch of the report.
  final Future<bool> Function()? probeDreamReport;

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
        action: Column(
          mainAxisSize: MainAxisSize.min,
          children: [_RecentChangesLink(), _DreamReportLink(probe: widget.probeDreamReport)],
        ),
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
            Center(child: _DreamReportLink(probe: widget.probeDreamReport)),
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

Future<bool> _defaultDreamProbe() async => await dream_api.getDreamReport(limit: 1) is ApiSuccess;

/// Shown only to accounts in the dream cohort: the report endpoint answers 404 for everyone else.
class _DreamReportLink extends StatefulWidget {
  const _DreamReportLink({this.probe});

  final Future<bool> Function()? probe;

  @override
  State<_DreamReportLink> createState() => _DreamReportLinkState();
}

class _DreamReportLinkState extends State<_DreamReportLink> {
  bool _available = false;

  @override
  void initState() {
    super.initState();
    (widget.probe ?? _defaultDreamProbe)().then((available) {
      if (mounted && available) setState(() => _available = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_available) return const SizedBox.shrink();
    return OmiButton.tertiary(
      key: const Key('review_dream_report'),
      label: context.l10n.dreamReportTitle,
      onPressed: () => routeToPage(context, const DreamReportPage()),
    );
  }
}
