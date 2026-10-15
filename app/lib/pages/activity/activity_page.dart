import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/review.dart' as review_api;
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

Future<({List<DailySummary> items, bool ok})> _loadActivityRecaps() => getDailySummaries(limit: 7, offset: 0);

/// What Omi did for the user, newest first: daily recaps and the changes it made on its own, each
/// with a way back to the full record. Questions stay in Review; this page asks for nothing.
///
/// Opening or leaving the page marks everything seen. A dot marks what arrived since the last visit,
/// and only for the delight items that light Home's bell.
class ActivityPage extends StatefulWidget {
  const ActivityPage({super.key, this.loadRecaps, this.loadChanges, this.seen, this.probeDreamReport});

  final RecentRecapsLoader? loadRecaps;
  final ReviewChangesLoader? loadChanges;
  final ActivitySeen? seen;
  final Future<bool> Function()? probeDreamReport;

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

class _ActivityPageState extends State<ActivityPage> {
  late final ActivitySeen _seen = widget.seen ?? ActivitySeen.instance;

  /// The last visit before this one: items newer than it get a dot.
  late final int _previousVisitMs;

  List<_ActivityItem> _items = const [];
  bool _loading = true;
  bool _failed = false;
  bool _hasChanges = false;

  @override
  void initState() {
    super.initState();
    _previousVisitMs = _seen.seenAtMs;
    _seen.markSeen();
    _refresh();
  }

  @override
  void dispose() {
    _seen.markSeen();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = _items.isEmpty;
      _failed = false;
    });
    final results = await Future.wait<Object>([
      (widget.loadRecaps ?? _loadActivityRecaps)(),
      (widget.loadChanges ?? review_api.getReviewChanges)(),
    ]);
    if (!mounted) return;
    final recaps = results[0] as ({List<DailySummary> items, bool ok});
    final changes = results[1] as ApiResult<ReviewChangesPage>;
    final items = <_ActivityItem>[
      if (recaps.ok) ...recaps.items.map(_RecapItem.new),
      if (changes case ApiSuccess(:final data)) ...data.changes.map(_ChangeItem.new),
    ]..sort((a, b) => b.at.compareTo(a.at));
    for (final recap in recaps.items) {
      _seen.reportDelight(recap.createdAt);
    }
    _seen.markSeen();
    setState(() {
      _loading = false;
      _failed = !recaps.ok && changes is ApiFailure;
      _hasChanges = changes is ApiSuccess<ReviewChangesPage> && changes.data.changes.isNotEmpty;
      _items = items;
    });
  }

  bool _isNew(_ActivityItem item) =>
      item is _RecapItem && _previousVisitMs > 0 && item.at.millisecondsSinceEpoch > _previousVisitMs;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final Widget body;
    if (_loading) {
      body = const OmiLoadingState();
    } else if (_failed) {
      body = OmiErrorState(message: l.reviewChangesLoadFailed, onRetry: _refresh);
    } else if (_items.isEmpty) {
      body = OmiEmptyState(
        icon: Icons.notifications_none,
        title: l.activityEmpty,
        action: DreamReportLink(probe: widget.probeDreamReport),
      );
    } else {
      final dates = OmiDateFormat.of(context);
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
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: [
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
                          onTap: () =>
                              routeToPage(context, DailySummaryDetailPage(summaryId: summary.id, summary: summary)),
                        ),
                      _ChangeItem(:final change) => _ActivityRow(
                          key: ValueKey('activity_change_${change.changeId}'),
                          leading: Icon(change.undone ? Icons.undo : reviewChangeIcon(change.kind),
                              size: 18, color: OmiColors.textSecondary),
                          title: change.title,
                          subtitle:
                              change.undone ? '${l.reviewChangeUndone} · ${dates.time(item.at)}' : dates.time(item.at),
                          isNew: false,
                          onTap: () => routeToPage(context, const RecentChangesPage()),
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
                  onPressed: () => routeToPage(context, const RecentChangesPage()),
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
      label: '$title, $subtitle',
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
