import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Recent daily recaps as a horizontal strip at the top of the conversations
/// page.
///
/// The strip is a fixed height whatever the recap count, so conversations stay
/// on screen — the reason this isn't the full-width card the recap list uses.
class DailyRecapsCarousel extends StatefulWidget {
  const DailyRecapsCarousel({super.key});

  @override
  State<DailyRecapsCarousel> createState() => DailyRecapsCarouselState();
}

class DailyRecapsCarouselState extends State<DailyRecapsCarousel> {
  /// A week of recaps. Anything older belongs on [DailyRecapsPage], which pages
  /// through the full history.
  static const int _limit = 7;

  static const double _cardWidth = 168;
  static const double _stripHeight = 150;

  List<DailySummary> _summaries = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final summaries = await getDailySummaries(limit: _limit, offset: 0);
    if (!mounted) return;
    setState(() {
      _summaries = summaries;
      _isLoading = false;
    });
  }

  /// Called by the conversations page's pull-to-refresh.
  Future<void> refresh() => _load();

  Future<void> _openSummary(DailySummary summary, int index) async {
    PlatformManager.instance.analytics.recapSummaryCardClicked(
      summaryId: summary.id,
      date: summary.date,
      cardIndex: index,
    );

    // The detail page pops with {deleted: true, summaryId} — drop the card so
    // the user doesn't come back to a ghost.
    final result = await Navigator.push<dynamic>(
      context,
      MaterialPageRoute(builder: (context) => DailySummaryDetailPage(summaryId: summary.id, summary: summary)),
    );
    if (!mounted) return;
    if (result is Map && result['deleted'] == true) {
      final deletedId = result['summaryId'] as String?;
      if (deletedId != null) {
        setState(() => _summaries.removeWhere((s) => s.id == deletedId));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) return _buildShimmer();
    // No recaps yet: stay out of the way rather than showing an empty state at
    // the top of a page that is about conversations.
    if (_summaries.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 4, 16, 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                context.l10n.dailyRecaps,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              TextButton(
                onPressed: () {
                  Navigator.push(context, MaterialPageRoute(builder: (context) => const DailyRecapsPage()));
                },
                style: TextButton.styleFrom(
                  foregroundColor: AppStyles.textTertiary,
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  context.l10n.viewAll,
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
                ),
              ),
            ],
          ),
        ),
        SizedBox(
          height: _stripHeight,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: _summaries.length,
            separatorBuilder: (_, __) => const SizedBox(width: 12),
            itemBuilder: (context, index) => _buildCard(_summaries[index], index),
          ),
        ),
      ],
    );
  }

  Widget _buildCard(DailySummary summary, int index) {
    return GestureDetector(
      onTap: () => _openSummary(summary, index),
      child: Container(
        width: _cardWidth,
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(20)),
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(10)),
                  alignment: Alignment.center,
                  child: Text(summary.dayEmoji, style: const TextStyle(fontSize: 18)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    formatCondensedRecapDate(summary.date),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 13, fontWeight: FontWeight.w500),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Expanded(
              child: Text(
                summary.headline,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500, height: 1.3),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (summary.stats.totalConversations > 0) ...[
                  const FaIcon(FontAwesomeIcons.solidComments, size: 10, color: Color(0xFF9A9BA1)),
                  const SizedBox(width: 4),
                  Text(
                    '${summary.stats.totalConversations}',
                    style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 13),
                  ),
                  const SizedBox(width: 10),
                ],
                if (summary.stats.actionItemsCount > 0) ...[
                  const FaIcon(FontAwesomeIcons.listCheck, size: 11, color: Color(0xFF9A9BA1)),
                  const SizedBox(width: 4),
                  Text(
                    '${summary.stats.actionItemsCount}',
                    style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 13),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmer() {
    // Same height as the loaded strip so the page doesn't jump when recaps land.
    return Padding(
      padding: const EdgeInsets.only(top: 36),
      child: SizedBox(
        height: _stripHeight,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: 3,
          separatorBuilder: (_, __) => const SizedBox(width: 12),
          itemBuilder: (context, index) => ShimmerWithTimeout(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              width: _cardWidth,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(20),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
