import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/conversations/widgets/daily_recap_recovery_action.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Every daily recap, as its own pushed page (nav audit #5): a back button leads out, and
/// pull-to-refresh reloads the recaps (hub audit #24). Home's "View All" opens it; the
/// Conversations tab never switches into a recap mode.
class DailyRecapsPage extends StatefulWidget {
  const DailyRecapsPage({super.key, this.fetchSummaries, this.createSummary});

  /// Injectable for tests; defaults to the recaps endpoint.
  final DailySummariesFetcher? fetchSummaries;
  final DailyRecapCreator? createSummary;

  @override
  State<DailyRecapsPage> createState() => _DailyRecapsPageState();
}

class _DailyRecapsPageState extends State<DailyRecapsPage> {
  final GlobalKey<DailySummariesListState> _listKey = GlobalKey<DailySummariesListState>();

  Future<void> _created(DailySummary summary) async {
    // Reload server pagination rather than inserting an older day into the
    // first page and making its length skip a row on the next page.
    await _listKey.currentState?.refresh();
    if (!mounted) return;
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => DailySummaryDetailPage(summaryId: summary.id, summary: summary),
    ));
    if (mounted) await _listKey.currentState?.refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.dailyRecaps),
        actions: [DailyRecapRecoveryAction(create: widget.createSummary, onCreated: _created)],
      ),
      body: RefreshIndicator(
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        onRefresh: () async {
          HapticFeedback.mediumImpact();
          await _listKey.currentState?.refresh();
        },
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            DailySummariesList(
              key: _listKey,
              fetchSummaries: widget.fetchSummaries,
              bottomPadding: MediaQuery.paddingOf(context).bottom + OmiSpacing.md,
            ),
          ],
        ),
      ),
    );
  }
}
