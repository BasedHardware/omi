import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';

typedef DailySummariesFetcher = Future<({List<DailySummary> items, bool ok})> Function({int limit, int offset});

/// Parses a recap's `YYYY-MM-DD` day. Null when malformed.
DateTime? parseRecapDate(String value) {
  final parts = value.split('-');
  if (parts.length != 3) return null;
  final year = int.tryParse(parts[0]);
  final month = int.tryParse(parts[1]);
  final day = int.tryParse(parts[2]);
  if (year == null || month == null || day == null) return null;
  return DateTime(year, month, day);
}

/// A recap's day as a group header ("Today", "Yesterday", "Wed, Sep 23"), in the reader's locale.
String recapDateLabel(BuildContext context, String value) {
  final date = parseRecapDate(value);
  return date == null ? value : OmiDateFormat.of(context).dayHeader(date);
}

/// The list of daily recaps (a sliver), shown by `DailyRecapsPage`.
///
/// Its first load, a failed load (with Try Again) and an empty answer each have one state
/// (docs/ux-contract.md §13). The page's pull-to-refresh calls [DailySummariesListState.refresh].
class DailySummariesList extends StatefulWidget {
  const DailySummariesList({super.key, this.fetchSummaries, this.bottomPadding = 0});

  /// Injectable for tests; defaults to the recaps endpoint.
  final DailySummariesFetcher? fetchSummaries;

  /// Space kept free after the last row.
  final double bottomPadding;

  @override
  State<DailySummariesList> createState() => DailySummariesListState();
}

class DailySummariesListState extends State<DailySummariesList> {
  List<DailySummary> _summaries = [];
  bool _isLoading = true;
  bool _isLoadingMore = false;
  static const int _limit = 20;
  bool _hasMore = true;
  bool _loadFailed = false;

  DailySummariesFetcher get _fetchSummaries => widget.fetchSummaries ?? getDailySummaries;

  @override
  void initState() {
    super.initState();
    _loadSummaries();
  }

  /// Reloads the first page (pull-to-refresh, Try Again).
  Future<void> refresh() => _loadSummaries(showSpinner: _summaries.isEmpty);

  Future<void> _loadSummaries({bool showSpinner = true}) async {
    if (showSpinner) setState(() => _isLoading = true);
    final result = await _fetchSummaries(limit: _limit, offset: 0);
    if (mounted) {
      setState(() {
        _isLoading = false;
        // A failed read is not "no recaps": keep what is on screen and leave
        // paging open so the next attempt can still load.
        _loadFailed = !result.ok;
        if (result.ok) {
          _summaries = result.items;
          _hasMore = result.items.length >= _limit;
        }
      });
    }
  }

  Future<void> _loadMore() async {
    if (_isLoadingMore || !_hasMore) return;
    setState(() => _isLoadingMore = true);
    // Derive the offset from the current list length so swipe-deletions don't
    // cause the next page to skip rows (a standalone counter would drift).
    final moreResult = await _fetchSummaries(limit: _limit, offset: _summaries.length);
    if (mounted) {
      setState(() {
        if (moreResult.ok) {
          _summaries.addAll(moreResult.items);
          _hasMore = moreResult.items.length >= _limit;
        }
        _isLoadingMore = false;
      });
    }
  }

  Future<void> _openSummary(DailySummary summary) async {
    // Track recap card click
    final cardIndex = _summaries.indexOf(summary);
    PlatformManager.instance.analytics.recapSummaryCardClicked(
      summaryId: summary.id,
      date: summary.date,
      cardIndex: cardIndex,
    );

    // Detail page pops with ``{deleted: true, summaryId}`` when the user deletes
    // from there — drop the row so they don't see a ghost card on return.
    final result = await routeToPage(context, DailySummaryDetailPage(summaryId: summary.id, summary: summary));
    if (!mounted) return;
    if (result is Map && result['deleted'] == true) {
      final deletedId = result['summaryId'] as String?;
      if (deletedId != null) {
        setState(() => _summaries.removeWhere((s) => s.id == deletedId));
      }
    }
  }

  /// Optimistic swipe-to-delete handler. Removes from the in-memory list
  /// before the API completes; on failure we restore the row + toast.
  Future<bool> _handleSwipeDelete(DailySummary summary) async {
    final confirmed = await showDeleteRecapConfirmDialog(context);
    if (confirmed != true) return false;

    // The await above can suspend long enough for the widget to be disposed,
    // and a concurrent list refresh can drop ``summary`` from ``_summaries``
    // (indexOf -> -1, which would make removeAt throw).
    if (!mounted) return false;
    final removedIndex = _summaries.indexOf(summary);
    if (removedIndex == -1) return false;
    setState(() => _summaries.removeAt(removedIndex));

    final ok = await deleteDailySummary(summary.id);
    if (!mounted) return ok;
    if (ok) {
      PlatformManager.instance.analytics.dailySummaryDeleted(
        summaryId: summary.id,
        date: summary.date,
        source: 'recap_list_swipe',
      );
      OmiFeedback.confirm(context, context.l10n.recapDeletedSnackbar);
    } else {
      // Restore so the user doesn't lose data we couldn't actually delete.
      setState(() => _summaries.insert(removedIndex, summary));
      PlatformManager.instance.analytics.dailySummaryDeleteFailed(
        summaryId: summary.id,
        date: summary.date,
        source: 'recap_list_swipe',
      );
      OmiFeedback.error(context, context.l10n.recapDeleteFailed);
    }
    return ok;
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return SliverToBoxAdapter(child: _buildLoadingShimmer());
    }

    if (_summaries.isEmpty) {
      final l10n = context.l10n;
      return SliverFillRemaining(
        hasScrollBody: false,
        child: _loadFailed
            ? OmiErrorState(message: l10n.somethingWentWrong, onRetry: _loadSummaries)
            : OmiEmptyState(
                icon: Icons.calendar_view_day_rounded,
                title: l10n.noDailyRecapsYet,
                message: l10n.dailyRecapsDescription,
              ),
      );
    }

    return SliverList(
      delegate: SliverChildBuilderDelegate((context, index) {
        // Extra tail item for spinner / bottom padding
        if (index == _summaries.length) {
          if (_isLoadingMore) {
            return const Padding(padding: EdgeInsets.all(OmiSpacing.md), child: Center(child: OmiSpinner()));
          }
          return SizedBox(height: widget.bottomPadding);
        }

        // Prefetch more when approaching end
        if (_hasMore && !_isLoadingMore && index >= _summaries.length - 3) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _loadMore());
        }

        return _buildSummaryCard(_summaries[index]);
      }, childCount: _summaries.length + 1),
    );
  }

  Widget _buildLoadingShimmer() {
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Column(
        children: List.generate(
          5,
          (index) => Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
            child: ShimmerWithTimeout(
              baseColor: AppStyles.backgroundSecondary,
              highlightColor: AppStyles.backgroundTertiary,
              child: Container(
                height: 80,
                decoration: const BoxDecoration(color: AppStyles.backgroundSecondary, borderRadius: OmiRadius.xlAll),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// "5 conversations · 3 tasks": every count says what it counts (hub audit #20).
  String _statsLabel(DailySummary summary) {
    final l10n = context.l10n;
    return [
      if (summary.stats.totalConversations > 0) l10n.conversationCount(summary.stats.totalConversations),
      if (summary.stats.actionItemsCount > 0) l10n.taskCount(summary.stats.actionItemsCount),
    ].join(' · ');
  }

  Widget _buildSummaryCard(DailySummary summary) {
    final l10n = context.l10n;
    final stats = _statsLabel(summary);
    const metaStyle = TextStyle(color: OmiColors.textTertiary, fontSize: 14);
    return Dismissible(
      key: ValueKey('daily-summary-${summary.id}'),
      direction: DismissDirection.endToStart,
      // The confirm dialog is the actual decision point — return false so the
      // framework doesn't ALSO remove the row (we manage ``_summaries``
      // ourselves so we can restore on API failure).
      confirmDismiss: (_) async {
        await _handleSwipeDelete(summary);
        return false;
      },
      background: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          decoration: const BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.xlAll),
          padding: const EdgeInsets.symmetric(horizontal: 24),
          alignment: Alignment.centerRight,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text(l10n.deleteRecap, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(width: 10),
              const Icon(Icons.delete_outline, color: Colors.white),
            ],
          ),
        ),
      ),
      child: GestureDetector(
        onTap: () => _openSummary(summary),
        child: Padding(
          padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
          child: Container(
            width: double.maxFinite,
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Emoji container - matches conversation list item
                  Container(
                    width: 40,
                    height: 40,
                    decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                    alignment: Alignment.center,
                    child: ExcludeSemantics(
                      child: Text(summary.dayEmoji, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w500)),
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
                        Text(
                          stats.isEmpty
                              ? recapDateLabel(context, summary.date)
                              : '${recapDateLabel(context, summary.date)} · $stats',
                          style: metaStyle,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
