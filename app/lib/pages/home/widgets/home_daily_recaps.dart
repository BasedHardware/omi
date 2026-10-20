import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/pages/home/widgets/home_for_you.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';
import 'package:omi/services/recap_events.dart';
import 'package:omi/services/proactivity/proactivity_push.dart';
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
  const HomeDailyRecaps({super.key, this.load = _loadRecentRecaps, this.loadFeed, this.outbox, this.openTarget});

  final RecentRecapsLoader load;
  final ProactivityFeedLoader? loadFeed;
  final ProactivityOutbox? outbox;
  final ProactivityTargetOpener? openTarget;

  @override
  State<HomeDailyRecaps> createState() => HomeDailyRecapsState();
}

class HomeDailyRecapsState extends State<HomeDailyRecaps> with WidgetsBindingObserver {
  final _forYouKey = GlobalKey<HomeForYouState>();
  List<DailySummary> _recaps = [];
  bool _loading = true;
  bool _loadFailed = false;

  StreamSubscription<String>? _deletions;
  StreamSubscription<void>? _arrivals;
  DateTime? _lastRefresh;

  /// A recap made while the app was in the background shows (and lights the Activity bell) on return.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    final last = _lastRefresh;
    if (last != null && DateTime.now().difference(last) < const Duration(minutes: 5)) return;
    refresh();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _deletions = recapDeletions.listen(_dropRecap);
    _arrivals = recapArrivals.listen((_) => refresh());
    WidgetsBinding.instance.addPostFrameCallback((_) => refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _deletions?.cancel();
    _arrivals?.cancel();
    super.dispose();
  }

  /// Reloads the row (pull-to-refresh on Home). A failed read keeps the cards already shown.
  Future<void> refresh() async {
    _lastRefresh = DateTime.now();
    await Future.wait([_refreshRecaps(), if (_forYouKey.currentState != null) _forYouKey.currentState!.refresh()]);
  }

  /// Load, arrival, resume and pull can overlap: only the newest response may land.
  int _generation = 0;

  Future<void> _refreshRecaps() async {
    final generation = ++_generation;
    if (!mounted) return;
    setState(() => _loading = _recaps.isEmpty);
    try {
      final result = await widget.load().timeout(const Duration(seconds: 15));
      if (!mounted || generation != _generation) return;
      final items = result.items.where((r) => !_deletedIds.contains(r.id)).toList();
      if (result.ok) ActivitySeen.instance.observe(ActivitySeen.recapArrivals(items));
      setState(() {
        if (result.ok) _recaps = items;
        _loadFailed = !result.ok;
        _loading = false;
      });
    } catch (_) {
      if (mounted && generation == _generation) setState(() => _loadFailed = true);
    } finally {
      if (mounted && generation == _generation) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildRecaps(context),
          widget.loadFeed == null
              ? HomeForYou(key: _forYouKey, outbox: widget.outbox, open: widget.openTarget)
              : HomeForYou(key: _forYouKey, load: widget.loadFeed!, outbox: widget.outbox, open: widget.openTarget),
        ],
      );

  Widget _buildRecaps(BuildContext context) {
    if (!_loading && _recaps.isEmpty) {
      return _loadFailed
          ? OmiErrorState(
              title: context.l10n.dailyRecaps, message: context.l10n.somethingWentWrong, onRetry: _refreshRecaps)
          : const SizedBox.shrink();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 8, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: GestureDetector(
                  onTap: _openAll,
                  child: Semantics(header: true, child: Text(context.l10n.dailyRecaps, style: OmiType.headline)),
                ),
              ),
              OmiButton.tertiary(label: context.l10n.viewAll, size: OmiButtonSize.compact, onPressed: _openAll),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 4),
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
        if (_loadFailed && !_loading)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: Row(children: [
              Expanded(
                  child: Text(context.l10n.somethingWentWrong,
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
              OmiButton.tertiary(label: context.l10n.tryAgain, onPressed: _refreshRecaps),
            ]),
          ),
      ],
    );
  }

  /// Recaps deleted while this row is mounted: a refresh already in flight may still return them.
  final Set<String> _deletedIds = {};

  /// A deleted recap leaves the row and the bell: the latest remaining recap is what counts.
  void _dropRecap(String id) {
    if (!mounted) return;
    _deletedIds.add(id);
    setState(() => _recaps.removeWhere((s) => s.id == id));
    ActivitySeen.instance.observe(ActivitySeen.recapArrivals(_recaps));
  }

  Future<void> _openAll() async {
    await routeToPage(context, const DailyRecapsPage());
    if (mounted) await _refreshRecaps();
  }

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
          if (deletedId != null) _dropRecap(deletedId);
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
