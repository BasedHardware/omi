import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:shimmer/shimmer.dart';

class DailySummariesList extends StatefulWidget {
  const DailySummariesList({super.key});

  @override
  State<DailySummariesList> createState() => _DailySummariesListState();
}

class _DailySummariesListState extends State<DailySummariesList> {
  List<DailySummary> _summaries = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  int _offset = 0;
  static const int _limit = 20;
  bool _hasMore = true;

  @override
  void initState() {
    super.initState();
    _loadSummaries();
  }

  Future<void> _loadSummaries() async {
    setState(() => _isLoading = true);
    final summaries = await getDailySummaries(limit: _limit, offset: 0);
    if (mounted) {
      setState(() {
        _summaries = summaries;
        _isLoading = false;
        _offset = summaries.length;
        _hasMore = summaries.length >= _limit;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_isLoadingMore || !_hasMore) return;
    setState(() => _isLoadingMore = true);
    final moreSummaries = await getDailySummaries(limit: _limit, offset: _offset);
    if (mounted) {
      setState(() {
        _summaries.addAll(moreSummaries);
        _offset += moreSummaries.length;
        _hasMore = moreSummaries.length >= _limit;
        _isLoadingMore = false;
      });
    }
  }

  void _openSummary(DailySummary summary) {
    // Track recap card click
    final cardIndex = _summaries.indexOf(summary);
    MixpanelManager().recapSummaryCardClicked(
      summaryId: summary.id,
      date: summary.date,
      cardIndex: cardIndex,
    );

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DailySummaryDetailPage(
          summaryId: summary.id,
          summary: summary,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return SliverToBoxAdapter(child: _buildLoadingShimmer());
    }

    if (_summaries.isEmpty) {
      return SliverToBoxAdapter(child: _buildEmptyState());
    }

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          // Extra tail item for spinner / bottom padding
          if (index == _summaries.length) {
            if (_isLoadingMore) {
              return Padding(
                padding: const EdgeInsets.all(16),
                child: Center(
                  child: SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.grey.shade400,
                    ),
                  ),
                ),
              );
            }
            return const SizedBox(height: 100);
          }

          // Prefetch more when approaching end
          if (_hasMore && !_isLoadingMore && index >= _summaries.length - 3) {
            WidgetsBinding.instance.addPostFrameCallback((_) => _loadMore());
          }

          return _buildSummaryCard(_summaries[index]);
        },
        childCount: _summaries.length + 1,
      ),
    );
  }

  Widget _buildLoadingShimmer() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: List.generate(
          5,
          (index) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Shimmer.fromColors(
              baseColor: AppStyles.backgroundSecondary,
              highlightColor: AppStyles.backgroundTertiary,
              child: Container(
                height: 80,
                decoration: BoxDecoration(
                  color: AppStyles.backgroundSecondary,
                  borderRadius: BorderRadius.circular(24),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(height: 40),
            const Text(
              '📊',
              style: TextStyle(fontSize: 64),
            ),
            const SizedBox(height: 16),
            Text(
              'No daily recaps yet',
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 18,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Your daily recaps will appear here once generated',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatCondensedDate(String dateStr) {
    // dateStr is in YYYY-MM-DD format
    final parts = dateStr.split('-');
    if (parts.length != 3) return dateStr;

    final year = int.tryParse(parts[0]) ?? 2024;
    final month = int.tryParse(parts[1]) ?? 1;
    final day = int.tryParse(parts[2]) ?? 1;

    final date = DateTime(year, month, day);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));

    // Check for Today and Yesterday
    if (date.year == today.year && date.month == today.month && date.day == today.day) {
      return 'Today';
    }
    if (date.year == yesterday.year && date.month == yesterday.month && date.day == yesterday.day) {
      return 'Yesterday';
    }

    const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    final weekday = weekdays[date.weekday - 1];
    final monthName = months[month - 1];

    return '$weekday, $monthName $day';
  }

  Widget _buildSummaryCard(DailySummary summary) {
    return GestureDetector(
      onTap: () => _openSummary(summary),
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(24.0),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Emoji container - matches conversation list item
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF35343B),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    summary.dayEmoji,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w500),
                  ),
                ),
                const SizedBox(width: 12),
                // Title and metadata
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        summary.headline,
                        style: Theme.of(context).textTheme.titleMedium,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 8),
                      // Date and stats with icons
                      Row(
                        children: [
                          Text(
                            _formatCondensedDate(summary.date),
                            style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 14),
                            maxLines: 1,
                          ),
                          if (summary.stats.totalConversations > 0) ...[
                            const Text(
                              ' • ',
                              style: TextStyle(color: Color(0xFF9A9BA1), fontSize: 14),
                            ),
                            const FaIcon(
                              FontAwesomeIcons.solidComments,
                              size: 10,
                              color: Color(0xFF9A9BA1),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '${summary.stats.totalConversations}',
                              style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 14),
                              maxLines: 1,
                            ),
                          ],
                          if (summary.stats.actionItemsCount > 0) ...[
                            const Text(
                              ' • ',
                              style: TextStyle(color: Color(0xFF9A9BA1), fontSize: 14),
                            ),
                            const FaIcon(
                              FontAwesomeIcons.listCheck,
                              size: 11,
                              color: Color(0xFF9A9BA1),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '${summary.stats.actionItemsCount}',
                              style: const TextStyle(color: Color(0xFF9A9BA1), fontSize: 14),
                              maxLines: 1,
                            ),
                          ],
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
