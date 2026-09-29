import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Loads recent daily recaps. Injectable so tests and the visual audit need no network.
typedef RecentRecapsLoader = Future<({List<DailySummary> items, bool ok})> Function();

Future<({List<DailySummary> items, bool ok})> _loadRecentRecaps() => getDailySummaries(limit: 3, offset: 0);

/// The Daily Recaps row at the top of Home: a header with View All and the latest recaps as
/// horizontally scrolling cards. Hidden entirely once loaded with no recaps.
class HomeDailyRecaps extends StatefulWidget {
  const HomeDailyRecaps({super.key, this.load = _loadRecentRecaps});

  final RecentRecapsLoader load;

  @override
  State<HomeDailyRecaps> createState() => HomeDailyRecapsState();
}

class HomeDailyRecapsState extends State<HomeDailyRecaps> {
  List<DailySummary> _recaps = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => refresh());
  }

  /// Reloads the row (pull-to-refresh on Home). A failed read keeps the cards already shown.
  Future<void> refresh() async {
    if (!mounted) return;
    setState(() => _loading = _recaps.isEmpty);
    final result = await widget.load();
    if (!mounted) return;
    setState(() {
      if (result.ok) _recaps = result.items;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_loading && _recaps.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 16, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: GestureDetector(
                  onTap: _openAll,
                  child: Semantics(header: true, child: Text(context.l10n.dailyRecaps, style: OmiType.headline)),
                ),
              ),
              OmiButton.secondary(label: context.l10n.viewAll, size: OmiButtonSize.compact, onPressed: _openAll),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 12, bottom: 4),
          child: SizedBox(
            height: DailySummaryCard.height,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.only(left: 16),
              itemCount: _loading ? 3 : _recaps.length,
              itemBuilder: (context, index) => Padding(
                padding: const EdgeInsets.only(right: 12),
                child: _loading ? const _RecapCardPlaceholder() : _card(context, _recaps[index]),
              ),
            ),
          ),
        ),
      ],
    );
  }

  void _openAll() => routeToPage(context, const DailyRecapsPage());

  Widget _card(BuildContext context, DailySummary summary) {
    return DailySummaryCard(
      summary: summary,
      dateLabel: recapDateLabel(context, summary.date),
      onTap: () async {
        PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: summary.id, date: summary.date);
        // The detail page pops with {deleted: true, summaryId} when the recap is deleted there;
        // drop its card instead of leaving it until the next refresh.
        final result = await routeToPage(context, DailySummaryDetailPage(summaryId: summary.id, summary: summary));
        if (!mounted) return;
        if (result is Map && result['deleted'] == true) {
          final deletedId = result['summaryId'] as String?;
          if (deletedId != null) setState(() => _recaps.removeWhere((s) => s.id == deletedId));
        }
      },
    );
  }
}

class _RecapCardPlaceholder extends StatelessWidget {
  const _RecapCardPlaceholder();

  @override
  Widget build(BuildContext context) {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface3,
      child: Container(
        width: DailySummaryCard.width,
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: const BorderRadius.all(Radius.circular(DailySummaryCard.radius)),
        ),
      ),
    );
  }
}
