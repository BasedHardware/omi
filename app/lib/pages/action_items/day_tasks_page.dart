import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart' show dayDateBounds;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef DayTasksFetcher = Future<ApiResult<ActionItemsResponse>> Function({
  required DateTime startDate,
  required DateTime endDate,
  int limit,
  int offset,
});

class DayTasksPage extends StatefulWidget {
  const DayTasksPage({super.key, required this.date, this.fetchTasks, this.api});

  final DateTime date;
  final DayTasksFetcher? fetchTasks;
  final ActionItemsApi? api;

  @override
  State<DayTasksPage> createState() => _DayTasksPageState();
}

class _DayTasksPageState extends State<DayTasksPage> {
  static const int _limit = 50;
  static const Duration _pageDeadline = Duration(seconds: 15);

  late DateTime _day = DateTime(widget.date.year, widget.date.month, widget.date.day);

  List<ActionItemWithMetadata> _tasks = [];
  bool _loading = true;
  bool _loadingMore = false;
  bool _failed = false;
  bool _refreshFailed = false;
  bool _loadMoreFailed = false;
  bool _truncated = false;
  bool _partial = false;
  bool _hasMore = false;
  int _offset = 0;
  int _generation = 0;

  DayTasksFetcher get _fetch =>
      widget.fetchTasks ??
      ({required endDate, limit = 50, offset = 0, required startDate}) =>
          (widget.api ?? ActionItemsApi(baseUrl: Env.apiBaseUrl ?? ''))
              .list(limit: limit, offset: offset, startDate: startDate, endDate: endDate);

  @override
  void initState() {
    super.initState();
    unawaited(_loadDay());
  }

  @override
  void dispose() {
    _generation++;
    super.dispose();
  }

  Future<ApiResult<ActionItemsResponse>> _page(DateTime start, DateTime end, int offset) async {
    try {
      return await _fetch(startDate: start, endDate: end, limit: _limit, offset: offset).timeout(_pageDeadline);
    } catch (_) {
      return const ApiFailure(ApiProblem(ApiProblemKind.transport));
    }
  }

  Future<void> _loadDay({bool clearRows = false}) async {
    final generation = ++_generation;
    final (start, end) = dayDateBounds(_day);
    setState(() {
      _loading = clearRows || _tasks.isEmpty;
      _loadingMore = false;
      _failed = false;
      _refreshFailed = false;
      _loadMoreFailed = false;
      _hasMore = false;
      _truncated = false;
      _partial = false;
      _offset = 0;
      if (clearRows) _tasks = [];
    });
    final result = await _page(start, end, 0);
    if (!mounted || generation != _generation) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiSuccess(:final data, :final truncated, :final rejectedRows):
          _tasks = data.actionItems;
          _offset = data.actionItems.length + rejectedRows;
          // A rejected wire row is independent: the offset already counts it,
          // so later valid tasks stay reachable by paging on. Keep the honest
          // partial notice, but only a server truncation ends pagination.
          _partial = rejectedRows > 0;
          _truncated = truncated || data.truncated;
          _hasMore = !_truncated && data.hasMore;
        case ApiFailure():
          if (_tasks.isEmpty) {
            _failed = true;
          } else {
            _refreshFailed = true;
          }
      }
    });
  }

  Future<void> _loadMore() async {
    if (_loading || _loadingMore || _failed || _truncated || !_hasMore) return;
    final generation = _generation;
    final (start, end) = dayDateBounds(_day);
    final offset = _offset;
    setState(() {
      _loadingMore = true;
      _loadMoreFailed = false;
    });
    final result = await _page(start, end, offset);
    if (!mounted || generation != _generation) return;
    setState(() {
      _loadingMore = false;
      switch (result) {
        case ApiSuccess(:final data, :final truncated, :final rejectedRows):
          _offset += data.actionItems.length + rejectedRows;
          final seen = _tasks.map((t) => t.id).toSet();
          _tasks = [..._tasks, ...data.actionItems.where((t) => seen.add(t.id))];
          // Same rule as the first page: rejected rows count toward the
          // offset but never end pagination on their own.
          _partial = _partial || rejectedRows > 0;
          _truncated = truncated || data.truncated || (data.actionItems.isEmpty && data.hasMore);
          _hasMore = !_truncated && data.hasMore;
        case ApiFailure():
          _loadMoreFailed = true;
      }
    });
  }

  void _goToDay(DateTime day) {
    _day = DateTime(day.year, day.month, day.day);
    unawaited(_loadDay(clearRows: true));
  }

  bool get _isToday {
    final now = DateTime.now();
    return _day.year == now.year && _day.month == now.month && _day.day == now.day;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        backgroundColor: OmiColors.surface0,
        elevation: 0,
        leading: Center(child: OmiBackButton.circled(fillColor: OmiColors.surface3)),
        title: Text('${l10n.tasks} · ${dates.dayHeader(_day)}', style: OmiType.headline),
        actions: [
          OmiIconButton.filled(
            key: const ValueKey('day_previous'),
            icon: const Icon(Icons.navigate_before),
            label: l10n.previousDay,
            fillColor: OmiColors.surface3,
            onPressed: () => _goToDay(DateTime(_day.year, _day.month, _day.day - 1)),
          ),
          OmiIconButton.filled(
            key: const ValueKey('day_next'),
            icon: const Icon(Icons.navigate_next),
            label: l10n.nextDay,
            fillColor: OmiColors.surface3,
            onPressed: _isToday ? null : () => _goToDay(DateTime(_day.year, _day.month, _day.day + 1)),
          ),
          const SizedBox(width: OmiSpacing.xs),
        ],
      ),
      body: RefreshIndicator(
        color: OmiColors.textPrimary,
        onRefresh: _loadDay,
        child: _buildBody(context, l10n, dates),
      ),
    );
  }

  Widget _buildBody(BuildContext context, AppLocalizations l10n, OmiDateFormat dates) {
    if (_loading) return const Center(child: OmiSpinner());
    if (_failed || (_truncated && _tasks.isEmpty)) {
      return _scrollable(OmiErrorState(message: l10n.somethingWentWrong, onRetry: _loadDay));
    }
    if (_tasks.isEmpty) {
      return _scrollable(OmiEmptyState(icon: Icons.check_circle_outline, title: l10n.noTasksOnDate(dates.date(_day))));
    }
    final extra = _refreshFailed ? 1 : 0;
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
      itemCount: _tasks.length + 1 + extra,
      itemBuilder: (context, index) {
        if (_refreshFailed && index == 0) {
          return Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: OmiErrorState(
              message: l10n.somethingWentWrong,
              onRetry: () => _loadDay(),
            ),
          );
        }
        index -= extra;
        if (index == _tasks.length) return _buildFooter(context, l10n);
        final task = _tasks[index];
        return Semantics(
          button: true,
          child: InkWell(
            onTap: () => showActionItemFormSheet(context, actionItem: task, onRefresh: () => unawaited(_loadDay())),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
                child: Row(
                  children: [
                    TaskCompletionMark(completed: task.completed),
                    const SizedBox(width: OmiSpacing.sm),
                    Expanded(
                      child:
                          Text(task.description, maxLines: 2, overflow: TextOverflow.ellipsis, style: OmiType.subhead),
                    ),
                    Icon(Icons.chevron_right, size: 18, color: OmiColors.textTertiary),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _scrollable(Widget child) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(child: child),
        ),
      ),
    );
  }

  Widget _buildFooter(BuildContext context, AppLocalizations l10n) {
    if (_loadMoreFailed) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
        child: Center(
          child: OmiButton.secondary(
            key: const ValueKey('day_tasks_retry'),
            label: l10n.tryAgain,
            size: OmiButtonSize.compact,
            onPressed: _loadMore,
          ),
        ),
      );
    }
    if (_loadingMore) {
      return const Padding(padding: EdgeInsets.symmetric(vertical: OmiSpacing.md), child: Center(child: OmiSpinner()));
    }
    if (_truncated) {
      return Padding(
        padding: const EdgeInsets.only(bottom: OmiSpacing.md),
        child: OmiPartialNotice(onRetry: () => _loadDay()),
      );
    }
    if (_hasMore) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Some wire rows were rejected, but paging continues: the offset
          // already skips them, so later valid tasks remain reachable.
          if (_partial)
            Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
              child: OmiPartialNotice(onRetry: () => _loadDay()),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
            child: Center(
              child: OmiButton.secondary(
                key: const ValueKey('day_tasks_load_more'),
                label: l10n.showMore,
                size: OmiButtonSize.compact,
                onPressed: _loadMore,
              ),
            ),
          ),
        ],
      );
    }
    if (_partial) {
      return Padding(
        padding: const EdgeInsets.only(bottom: OmiSpacing.md),
        child: OmiPartialNotice(onRetry: () => _loadDay()),
      );
    }
    return const SizedBox.shrink();
  }
}
