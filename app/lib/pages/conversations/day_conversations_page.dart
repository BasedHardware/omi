import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';

typedef DayConversationsFetcher = Future<({List<ServerConversation> items, bool ok, bool truncated})> Function({
  required DateTime startDate,
  required DateTime endDate,
  int limit,
  int offset,
});

(DateTime start, DateTime end) dayDateBounds(DateTime day) {
  final start = DateTime(day.year, day.month, day.day);
  return (start, DateTime(day.year, day.month, day.day + 1).subtract(const Duration(microseconds: 1)));
}

class DayConversationsPage extends StatefulWidget {
  const DayConversationsPage({super.key, required this.date, this.fetchConversations});

  final DateTime date;
  final DayConversationsFetcher? fetchConversations;

  @override
  State<DayConversationsPage> createState() => _DayConversationsPageState();
}

class _DayConversationsPageState extends State<DayConversationsPage> {
  static const int _limit = 50;
  static const Duration _pageDeadline = Duration(seconds: 15);

  late DateTime _day = DateTime(widget.date.year, widget.date.month, widget.date.day);
  late final ConversationProvider _provider = ConversationProvider(isSignedIn: () => AuthService.instance.isSignedIn());

  bool _loading = true;
  bool _loadingMore = false;
  bool _failed = false;
  bool _refreshFailed = false;
  bool _loadMoreFailed = false;
  bool _truncated = false;
  bool _hasMore = true;
  int _offset = 0;
  int _generation = 0;

  late final ConversationApi _api = ConversationApi(baseUrl: Env.apiBaseUrl ?? '');

  DayConversationsFetcher get _fetch =>
      widget.fetchConversations ??
      ({required endDate, limit = 50, offset = 0, required startDate}) async {
        // Row-by-row decode: one malformed conversation must not hide every
        // other valid row for the day behind an error. Rejected rows surface
        // as partial data instead.
        final result = await _api.list(
            limit: limit, offset: offset, includeDiscarded: false, startDate: startDate, endDate: endDate);
        return switch (result) {
          ApiSuccess(:final data, :final truncated, :final rejectedRows) => (
              items: data,
              ok: true,
              truncated: truncated || rejectedRows > 0,
            ),
          ApiFailure() => (items: <ServerConversation>[], ok: false, truncated: false),
        };
      };

  @override
  void initState() {
    super.initState();
    unawaited(_loadDay());
  }

  @override
  void dispose() {
    _generation++;
    _provider.dispose();
    super.dispose();
  }

  Future<({List<ServerConversation> items, bool ok, bool truncated})> _page(
      DateTime start, DateTime end, int offset) async {
    try {
      return await _fetch(startDate: start, endDate: end, limit: _limit, offset: offset).timeout(_pageDeadline);
    } catch (_) {
      return (items: <ServerConversation>[], ok: false, truncated: false);
    }
  }

  Future<void> _loadDay({bool clearRows = false}) async {
    final generation = ++_generation;
    final (start, end) = dayDateBounds(_day);
    setState(() {
      _loading = clearRows || _provider.conversations.isEmpty;
      _loadingMore = false;
      _failed = false;
      _refreshFailed = false;
      _loadMoreFailed = false;
      _truncated = false;
      _hasMore = false;
      _offset = 0;
      if (clearRows) {
        _provider.conversations = [];
        _provider.groupedConversations = {};
      }
    });
    final result = await _page(start, end, 0);
    if (!mounted || generation != _generation) return;
    setState(() {
      _loading = false;
      if (!result.ok) {
        if (_provider.conversations.isEmpty) {
          _failed = true;
        } else {
          _refreshFailed = true;
        }
        return;
      }
      _provider.conversations = result.items;
      _provider.groupConversationsByDate();
      _offset = result.items.length;
      _truncated = result.truncated;
      _hasMore = !result.truncated && result.items.length >= _limit;
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
      if (!result.ok) {
        _loadMoreFailed = true;
        return;
      }
      _offset += result.items.length;
      final seen = _provider.conversations.map((c) => c.id).toSet();
      _provider.conversations = [..._provider.conversations, ...result.items.where((c) => seen.add(c.id))];
      _provider.groupConversationsByDate();
      _truncated = result.truncated;
      _hasMore = !result.truncated && result.items.length >= _limit;
    });
  }

  void _goToDay(DateTime day) {
    _day = DateTime(day.year, day.month, day.day);
    unawaited(_loadDay(clearRows: true));
  }

  Future<void> _pickDay() async {
    await showConversationDateRangePicker(
      context,
      initialStartDate: _day,
      initialEndDate: _day,
      singleDayOnly: true,
      onSelected: (start, _) => _goToDay(start),
    );
  }

  bool get _isToday {
    final now = DateTime.now();
    return _day.year == now.year && _day.month == now.month && _day.day == now.day;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    return ChangeNotifierProvider<ConversationProvider>.value(
      value: _provider,
      child: Scaffold(
        backgroundColor: OmiColors.surface0,
        appBar: AppBar(
          backgroundColor: OmiColors.surface0,
          elevation: 0,
          leading: Center(child: OmiBackButton.circled(fillColor: OmiColors.surface3)),
          title: Text(dates.dayHeader(_day), style: OmiType.headline),
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
            OmiIconButton.filled(
              key: const ValueKey('day_calendar'),
              icon: const Icon(Icons.calendar_month_outlined, size: 18),
              label: l10n.filterByDate,
              fillColor: OmiColors.surface3,
              onPressed: _pickDay,
            ),
            const SizedBox(width: OmiSpacing.xs),
          ],
        ),
        body: RefreshIndicator(
          color: OmiColors.textPrimary,
          onRefresh: _loadDay,
          child: ListenableBuilder(
            listenable: _provider,
            builder: (context, _) => _buildBody(context, l10n, dates),
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context, AppLocalizations l10n, OmiDateFormat dates) {
    if (_loading) return const Center(child: OmiSpinner());
    if (_failed || (_truncated && _provider.displayedConversations.isEmpty)) {
      return _scrollable(OmiErrorState(message: l10n.somethingWentWrong, onRetry: _loadDay));
    }
    final conversations = _provider.displayedConversations;
    if (conversations.isEmpty) {
      return _scrollable(OmiEmptyState(
        icon: Icons.forum_outlined,
        title: l10n.noConversationsOnDate(dates.date(_day)),
      ));
    }
    final extra = _refreshFailed ? 1 : 0;
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
      itemCount: conversations.length + 1 + extra,
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
        if (index == conversations.length) {
          return _buildFooter(context, l10n);
        }
        final conversation = conversations[index];
        return ConversationListItem(
          key: ValueKey(conversation.id),
          conversation: conversation,
          date: conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt),
          conversationIdx: index,
          allowSelection: false,
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
            key: const ValueKey('day_load_more_retry'),
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
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
        child: Center(
          child: OmiButton.secondary(
            key: const ValueKey('day_load_more'),
            label: l10n.showMore,
            size: OmiButtonSize.compact,
            onPressed: _loadMore,
          ),
        ),
      );
    }
    return const SizedBox.shrink();
  }
}
