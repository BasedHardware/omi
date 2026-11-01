import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/review.dart' as review_api;
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/needs_attention_section.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/recap_events.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

Future<({List<DailySummary> items, bool ok})> _loadActivityRecaps() => getDailySummaries(limit: 7, offset: 0);

/// What Omi did for the user, newest first: daily recaps and the changes it made on its own, each
/// with a way back to the full record. Questions stay in Review; this page asks for nothing.
///
/// Opening or leaving the page marks everything seen. A dot marks what arrived since the last visit,
/// and only for the delight items that light Home's bell.
///
/// Work that could not finish sits above the feed in a Needs attention section; showing it marks it
/// seen on every device.
class ActivityPage extends StatefulWidget {
  const ActivityPage({
    super.key,
    this.loadRecaps,
    this.loadChanges,
    this.seen,
    this.probeDreamReport,
    this.pendingWork,
    this.captureWedgeMonitor,
  });

  final RecentRecapsLoader? loadRecaps;
  final ReviewChangesLoader? loadChanges;
  final ActivitySeen? seen;
  final Future<bool> Function()? probeDreamReport;

  /// Injectable for tests; defaults to [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  /// Injectable for tests and visual audits; defaults to [CaptureWedgeMonitor.instance].
  final CaptureWedgeMonitor? captureWedgeMonitor;

  @override
  State<ActivityPage> createState() => _ActivityPageState();
}

sealed class _ActivityItem {
  const _ActivityItem(this.at);
  final DateTime at;
}

class _RecapItem extends _ActivityItem {
  _RecapItem(this.summary) : super(summary.createdAt.toLocal());
  final DailySummary summary;
}

class _ChangeItem extends _ActivityItem {
  _ChangeItem(this.change) : super(change.createdAt.toLocal());
  final ReviewChange change;
}

class _ActivityPageState extends State<ActivityPage> with WidgetsBindingObserver {
  late final ActivitySeen _seen = widget.seen ?? ActivitySeen.instance;
  late final PendingWorkStore _pendingWork = widget.pendingWork ?? PendingWorkStore.instance;
  late final CaptureWedgeMonitor _captureMonitor = widget.captureWedgeMonitor ?? CaptureWedgeMonitor.instance;

  /// The last visit before this one: items newer than it get a dot.
  late final int _previousVisitMs;

  /// Each source's last good rows, so a refresh where one source fails keeps that source's rows.
  List<DailySummary> _recaps = const [];
  List<ReviewChange> _changes = const [];
  List<_ActivityItem> _items = const [];
  bool _loading = true;
  bool _failed = false;
  bool _hasChanges = false;

  /// One source failed for a reason other than "not available for this account": what loaded is
  /// shown, with a retry, instead of passing for a complete list.
  bool _partial = false;

  /// When this page last loaded: leaving marks seen only through what it actually showed.
  /// Null until a recap load succeeds: a failed load must not clear a bell the user never saw.
  DateTime? _shownThrough;
  StreamSubscription<void>? _arrivals;

  /// Rebuild when capture attention arrives or leaves: an empty feed otherwise
  /// commits the build to the empty-state branch, where nothing listens to the
  /// monitor, and a capture problem that begins while the reader stays on the
  /// page would light the bell without ever showing its row.
  void _onCaptureAttentionChanged() {
    if (mounted) setState(() {});
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _previousVisitMs = _seen.seenAtMs;
    _captureMonitor.addListener(_onCaptureAttentionChanged);
    // A daily-summary notification while Activity is on screen shows here, not only on Home.
    _arrivals = recapArrivals.listen((_) => _refresh());
    _refresh();
  }

  /// A recap made while the app was in the background shows here on return, not just on Home.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _captureMonitor.removeListener(_onCaptureAttentionChanged);
    _arrivals?.cancel();
    final shown = _shownThrough;
    if (shown != null) _seen.markSeen(through: shown);
    super.dispose();
  }

  /// Only the newest refresh may land: an older, slower one must not revert rows or move the seen
  /// watermark backward.
  int _generation = 0;

  /// Recaps deleted from this page: a refresh already in flight may still return them.
  final Set<String> _deletedIds = {};

  Future<void> _refresh() async {
    final generation = ++_generation;
    setState(() {
      _loading = _items.isEmpty;
      _failed = false;
    });
    final startedAt = DateTime.now();
    final results = await Future.wait<Object>([
      (widget.loadRecaps ?? _loadActivityRecaps)(),
      (widget.loadChanges ?? review_api.getReviewChanges)(),
      _pendingWork.refresh().then((_) => true),
    ]);
    if (!mounted || generation != _generation) return;
    // The section is on screen now: its items stop lighting the bell here and on the Mac.
    unawaited(_pendingWork.markSeen());
    final loaded = results[0] as ({List<DailySummary> items, bool ok});
    // A refresh that started before a deletion may still return the deleted recap.
    final recaps = (items: loaded.items.where((r) => !_deletedIds.contains(r.id)).toList(), ok: loaded.ok);
    final changes = results[1] as ApiResult<ReviewChangesPage>;
    if (recaps.ok) _recaps = recaps.items;
    switch (changes) {
      case ApiSuccess(:final data):
        _changes = data.changes;
      // Review changes answer 404 for accounts outside the Review cohort: absent, not failed.
      case ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound:
        _changes = const [];
      case ApiFailure():
        break;
    }
    final changesFailed = changes is ApiFailure<ReviewChangesPage> && changes.problem.kind != ApiProblemKind.notFound;
    final anyFailed = !recaps.ok || changesFailed;
    if (recaps.ok) {
      _seen.observe(ActivitySeen.recapArrivals(recaps.items));
      // Through the newest recap shown, too: a server clock ahead of the phone's must not leave a
      // recap already seen lighting the bell. Recaps that arrive after this load are still news.
      var through = _shownThrough != null && _shownThrough!.isAfter(startedAt) ? _shownThrough! : startedAt;
      for (final at in ActivitySeen.recapArrivals(recaps.items)) {
        if (at.isAfter(through)) through = at;
      }
      _shownThrough = through;
    }
    final shown = _shownThrough;
    if (shown != null) _seen.markSeen(through: shown);
    setState(() {
      _loading = false;
      _rebuildItems();
      _failed = anyFailed && _items.isEmpty;
      _partial = anyFailed && _items.isNotEmpty;
    });
  }

  void _rebuildItems() {
    _hasChanges = _changes.isNotEmpty;
    _items = <_ActivityItem>[..._recaps.map(_RecapItem.new), ..._changes.map(_ChangeItem.new)]
      ..sort((a, b) => b.at.compareTo(a.at));
  }

  /// Recent Changes can Undo or Redo in place and returns nothing: reload on return so the rows here
  /// match what it changed.
  Future<void> _openRecentChanges() async {
    await routeToPage(context, const RecentChangesPage());
    if (mounted) await _refresh();
  }

  /// The detail page pops `{deleted: true, summaryId}` when the recap is deleted there (and announces
  /// it to Home's recap row itself): drop it here instead of leaving a ghost.
  Future<void> _openRecap(DailySummary summary) async {
    final result = await routeToPage(context, DailySummaryDetailPage(summaryId: summary.id, summary: summary));
    if (!mounted || result is! Map || result['deleted'] != true) return;
    final deletedId = result['summaryId'] as String? ?? summary.id;
    _deletedIds.add(deletedId);
    setState(() {
      _recaps = _recaps.where((r) => r.id != deletedId).toList();
      _rebuildItems();
    });
    _seen.observe(ActivitySeen.recapArrivals(_recaps));
  }

  bool _isNew(_ActivityItem item) =>
      item is _RecapItem &&
      item.summary.createdAtKnown &&
      _previousVisitMs > 0 &&
      item.at.millisecondsSinceEpoch > _previousVisitMs;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final attention = NeedsAttentionSection(store: _pendingWork, captureMonitor: _captureMonitor);
    final hasAttention =
        NeedsAttentionSection.hasContent(_pendingWork, context.watch<SyncProvider?>(), _captureMonitor);
    final Widget body;
    if (_loading) {
      body = const OmiLoadingState();
    } else if (_failed) {
      body = OmiErrorState(message: l.activityLoadFailed, onRetry: _refresh);
    } else if (_items.isEmpty && !hasAttention) {
      // Still pullable: a recap that lands while the page is open is one pull away.
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: LayoutBuilder(
          builder: (context, constraints) => SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: Center(
                child: OmiEmptyState(
                  icon: Icons.notifications_none,
                  title: l.activityEmpty,
                  action: DreamReportLink(probe: widget.probeDreamReport),
                ),
              ),
            ),
          ),
        ),
      );
    } else {
      final dates = OmiDateFormat.of(context);
      // The capture rows are on screen in this build (the failed/empty branches
      // above never mount the section). Marking after the frame — not in the
      // load path — keeps the bell lit when a failed load would have hidden
      // rows the user never saw, and covers attention that arrives while the
      // page is already open. Only the episodes this build included count as
      // seen: an incident declared after the build stays unseen until a frame
      // shows its row, so a stale callback cannot extinguish the bell first.
      final builtThrough = <DateTime>[
        if (_captureMonitor.storageAtRisk != null) _captureMonitor.storageAtRisk!.engagedAt,
        if (_captureMonitor.uploadStall != null) _captureMonitor.uploadStall!.since,
        if (_captureMonitor.acuteEpisode != null) _captureMonitor.acuteEpisode!.declaredAt,
      ].fold<DateTime?>(null, (a, b) => a == null || b.isAfter(a) ? b : a);
      // A build with no capture rows shows nothing to mark seen; advancing the
      // timestamp then would be the stale-callback bug this snapshot prevents.
      if (builtThrough != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _captureMonitor.markCaptureAttentionSeen(through: builtThrough);
        });
      }
      final groups = <(String, List<_ActivityItem>)>[];
      for (final item in _items) {
        final header = dates.dayHeader(item.at);
        if (groups.isEmpty || groups.last.$1 != header) groups.add((header, []));
        groups.last.$2.add(item);
      }
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          // A short feed must still overscroll, or pull-to-refresh never arms on Android.
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: [
            if (_partial)
              Padding(
                padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
                child: OmiPartialNotice(message: l.activityLoadFailed, onRetry: _refresh),
              ),
            attention,
            for (final (header, items) in groups) ...[
              _DayHeader(label: header),
              _ActivityGroup(
                children: [
                  for (final item in items)
                    switch (item) {
                      _RecapItem(:final summary) => _ActivityRow(
                          key: ValueKey('activity_recap_${summary.id}'),
                          leading: summary.dayEmoji.isEmpty
                              ? Icon(Icons.calendar_today_outlined, size: 18, color: OmiColors.textSecondary)
                              : Text(summary.dayEmoji, style: OmiType.title3),
                          title: summary.headline,
                          subtitle: '${l.recap} · ${dates.time(item.at)}',
                          isNew: _isNew(item),
                          onTap: () => _openRecap(summary),
                        ),
                      _ChangeItem(:final change) => _ActivityRow(
                          key: ValueKey('activity_change_${change.changeId}'),
                          leading: Icon(change.undone ? Icons.undo : reviewChangeIcon(change.kind),
                              size: 18, color: OmiColors.textSecondary),
                          title: change.title,
                          subtitle:
                              change.undone ? '${l.reviewChangeUndone} · ${dates.time(item.at)}' : dates.time(item.at),
                          isNew: false,
                          onTap: _openRecentChanges,
                        ),
                    },
                ],
              ),
            ],
            const SizedBox(height: OmiSpacing.md),
            if (_hasChanges)
              Center(
                child: OmiButton.tertiary(
                  key: const Key('activity_recent_changes'),
                  label: l.reviewRecentChanges,
                  onPressed: _openRecentChanges,
                ),
              ),
            Center(child: DreamReportLink(probe: widget.probeDreamReport)),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l.activity)),
      body: body,
    );
  }
}

class _DayHeader extends StatelessWidget {
  const _DayHeader({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.xs),
      child: Semantics(
        header: true,
        child: Text(
          label.toUpperCase(),
          style: OmiType.footnote
              .copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary, letterSpacing: 0.4),
        ),
      ),
    );
  }
}

class _ActivityGroup extends StatelessWidget {
  const _ActivityGroup({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: OmiColors.surface1,
      borderRadius: OmiRadius.xlAll,
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          for (var i = 0; i < children.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 1, indent: 64, color: OmiColors.surface2),
            children[i],
          ],
        ],
      ),
    );
  }
}

class _ActivityRow extends StatelessWidget {
  const _ActivityRow({
    super.key,
    required this.leading,
    required this.title,
    required this.subtitle,
    required this.isNew,
    required this.onTap,
  });

  final Widget leading;
  final String title;
  final String subtitle;
  final bool isNew;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: isNew ? '$title, $subtitle, ${context.l10n.activityNewItem}' : '$title, $subtitle',
      onTap: onTap,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 14, 14),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                alignment: Alignment.center,
                child: leading,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: OmiType.body, maxLines: 2, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 3),
                    Text(subtitle, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              if (isNew)
                Container(
                  key: const Key('activity_new_dot'),
                  margin: const EdgeInsetsDirectional.only(start: OmiSpacing.xs),
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
