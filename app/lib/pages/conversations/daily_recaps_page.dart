import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Every daily recap, as its own pushed page (nav audit #5): a back button leads out, and
/// pull-to-refresh reloads the recaps (hub audit #24). Home's "View All" opens it; the
/// Conversations tab never switches into a recap mode.
class DailyRecapsPage extends StatefulWidget {
  const DailyRecapsPage({super.key, this.fetchSummaries});

  /// Injectable for tests; defaults to the recaps endpoint.
  final DailySummariesFetcher? fetchSummaries;

  @override
  State<DailyRecapsPage> createState() => _DailyRecapsPageState();
}

class _DailyRecapsPageState extends State<DailyRecapsPage> {
  final GlobalKey<DailySummariesListState> _listKey = GlobalKey<DailySummariesListState>();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.dailyRecaps)),
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
