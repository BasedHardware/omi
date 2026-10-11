import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/utils/logger.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;
import 'package:omi/pages/conversations/conversation_map_page.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/pages/conversations/widgets/folder_options_sheet.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/ui/navigation/omi_edge_swipe.dart';
import 'package:omi/utils/conversations/date_query.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

/// How long the search panel takes to drop in, and to lift away.
const Duration kSearchDropDuration = Duration(milliseconds: 440);
const Duration kSearchLiftDuration = Duration(milliseconds: 260);

/// A drop with a small overshoot, so the panel lands like a sheet pulled down from the top edge.
const Curve kSearchDropCurve = Cubic(0.2, 0.9, 0.25, 1.08);

/// Opens search over the Home shell: the page dims while the panel drops from the top. Before
/// anything is typed it shows tiles to browse by folder, recap, memory, person and place;
/// typing searches conversations, recaps, tasks and memories at once.
Future<void> showGlobalSearch(BuildContext context, {String? initialQuery, GlobalSearchSource? source}) {
  return Navigator.of(context).push<void>(
    SearchDropRoute<void>(
      builder: (_) => GlobalSearchPage(initialQuery: initialQuery, source: source ?? const ApiGlobalSearchSource()),
    ),
  );
}

/// The search panel's route: not opaque, so the dimmed shell stays painted underneath.
class SearchDropRoute<T> extends PageRoute<T> with OmiEdgeSwipeRoute<T> {
  SearchDropRoute({required this.builder, super.settings}) : super(fullscreenDialog: true);

  final WidgetBuilder builder;

  @override
  bool get opaque => false;

  @override
  bool get barrierDismissible => false;

  @override
  Color? get barrierColor => null;

  @override
  String? get barrierLabel => null;

  @override
  bool get maintainState => true;

  @override
  Duration get transitionDuration => kSearchDropDuration;

  @override
  Duration get reverseTransitionDuration => kSearchLiftDuration;

  @override
  Widget buildPage(BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation) =>
      wrapEdgeSwipe(context, builder(context));

  @override
  Widget buildTransitions(
      BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation, Widget child) {
    return SearchDropTransition(animation: animation, horizontalMotion: edgeSwipeInProgress, child: child);
  }

  @override
  void dispose() {
    disposeEdgeSwipe();
    super.dispose();
  }
}

/// The drop itself, separate from the route so tests and the visual audit can pump one frame of it.
class SearchDropTransition extends StatelessWidget {
  const SearchDropTransition({super.key, required this.animation, required this.child, this.horizontalMotion = false});

  final Animation<double> animation;
  final Widget child;

  final bool horizontalMotion;

  @override
  Widget build(BuildContext context) {
    final drop = horizontalMotion
        ? animation
        : CurvedAnimation(parent: animation, curve: kSearchDropCurve, reverseCurve: Curves.easeInCubic);
    final dim = horizontalMotion ? animation : CurvedAnimation(parent: animation, curve: Curves.easeOut);
    return Stack(
      fit: StackFit.expand,
      children: [
        IgnorePointer(
          child: FadeTransition(opacity: dim, child: ColoredBox(color: Colors.black.withValues(alpha: 0.18))),
        ),
        SlideTransition(
          position: Tween<Offset>(begin: horizontalMotion ? const Offset(1, 0) : const Offset(0, -1), end: Offset.zero)
              .animate(drop),
          child: child,
        ),
      ],
    );
  }
}

/// Where search reads from. The API source is production; tests and the visual audit pass fakes.
abstract class GlobalSearchSource {
  const GlobalSearchSource();

  Future<ApiResult<SearchOverview>> overview();
  Future<ConversationSearchResult> conversations(String query,
      {String? speakerId, DateTime? startDate, DateTime? endDate});
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false});
  Future<ApiResult<List<DailySummary>>> recaps(String query);
  Future<ApiResult<List<DailySummary>>> recapsInRange(String query, DateTime start, DateTime end) => recaps(query);
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query);
  Future<ApiResult<List<MemorySearchHit>>> memories(String query);
}

String _dayKey(DateTime day) =>
    '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

class ApiGlobalSearchSource extends GlobalSearchSource {
  const ApiGlobalSearchSource();

  @override
  Future<ApiResult<SearchOverview>> overview() => getSearchOverview();

  @override
  Future<ConversationSearchResult> conversations(String query,
          {String? speakerId, DateTime? startDate, DateTime? endDate}) =>
      searchConversationsServerResult(query,
          limit: 20, includeDiscarded: false, speakerId: speakerId, startDate: startDate, endDate: endDate);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) =>
      getConversations(limit: 50, folderId: folderId, starred: starred ? true : null);

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) => searchDailySummaries(query);

  @override
  Future<ApiResult<List<DailySummary>>> recapsInRange(String query, DateTime start, DateTime end) async {
    final firstDay = DateTime(start.year, start.month, start.day);
    final lastDay = DateTime(end.year, end.month, end.day);
    if (lastDay.isBefore(firstDay)) return const ApiSuccess(<DailySummary>[]);
    final firstKey = _dayKey(firstDay);
    final lastKey = _dayKey(lastDay);
    // The list API has no date parameters, so page its reverse-chronological
    // results once, collecting every recap whose day falls inside the range.
    // Five pages cover the same 365-day history window as recap search with
    // room for sparse days. The listing is newest-first, so a range is one
    // contiguous block: keep paging until a page's oldest row predates the
    // range (or the listing ends) so a block straddling a page boundary is
    // still collected whole.
    final byDay = <String, DailySummary>{};
    for (var offset = 0; offset < 500; offset += 100) {
      final result = await getDailySummaries(limit: 100, offset: offset);
      if (!result.ok) return const ApiFailure(ApiProblem(ApiProblemKind.transport));
      for (final recap in result.items) {
        final day = recap.date;
        if (day.compareTo(lastKey) <= 0 && day.compareTo(firstKey) >= 0) byDay[day] = recap;
      }
      if (result.items.length < 100 || result.items.isEmpty || result.items.last.date.compareTo(firstKey) < 0) {
        break;
      }
    }
    if (byDay.isEmpty) return const ApiSuccess(<DailySummary>[]);
    final collected = byDay.values.toList()..sort((a, b) => a.date.compareTo(b.date));
    return ApiSuccess(collected);
  }

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) => searchActionItems(query);

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) => searchMemories(query);
}

class _Results {
  const _Results({
    this.conversations = const [],
    this.recaps = const [],
    this.tasks = const [],
    this.memories = const [],
    this.partial = false,
  });

  final List<ServerConversation> conversations;
  final List<DailySummary> recaps;
  final List<ActionItemWithMetadata> tasks;
  final List<MemorySearchHit> memories;

  /// At least one kind of result failed to load, so what is shown (or its absence) is incomplete.
  final bool partial;

  bool get isEmpty => conversations.isEmpty && recaps.isEmpty && tasks.isEmpty && memories.isEmpty;
}

/// A browsed list opened from a tile: a folder, Starred, or the people.
class _Scope {
  const _Scope({required this.title, this.folderId, this.starred = false, this.people = false});

  final String title;
  final String? folderId;
  final bool starred;
  final bool people;
}

const String _recentSearchesKey = 'globalSearchRecentQueries';
const int _recentSearchesMax = 6;

class GlobalSearchPage extends StatefulWidget {
  const GlobalSearchPage({super.key, this.initialQuery, required this.source});

  final String? initialQuery;
  final GlobalSearchSource source;

  @override
  State<GlobalSearchPage> createState() => _GlobalSearchPageState();
}

class _GlobalSearchPageState extends State<GlobalSearchPage> {
  late final TextEditingController _query = TextEditingController(text: widget.initialQuery ?? '');
  final FocusNode _focus = FocusNode();
  Timer? _debounce;
  int _generation = 0;

  SearchOverview? _overview;
  List<String> _recent = const [];

  bool _searching = false;
  _Results _results = const _Results();

  _Scope? _scope;
  bool _loadingScope = false;
  List<ServerConversation> _scopeConversations = const [];

  /// In the People scope the search field filters the shared people list instead of searching.
  String _peopleQuery = '';

  ConversationDateQuery _dateQuery = const ConversationDateQuery(query: '');
  DateTime? _pickedStart;
  DateTime? _pickedEnd;

  DateTime? get _activeStart => _dateQuery.startDate ?? _pickedStart;
  DateTime? get _activeEnd => _dateQuery.endDate ?? _pickedEnd;

  /// The query actually searched: the typed text with any date phrase
  /// stripped. Rows match this text, so navigation that filters by query
  /// (memories) must reuse it, not the raw field content.
  String get _searchedQuery => _activeStart != null || _activeEnd != null ? _dateQuery.query : _query.text.trim();

  @override
  void initState() {
    super.initState();
    _recent = SharedPreferencesUtil().getStringList(_recentSearchesKey);
    unawaited(_loadOverview());
    if (_query.text.trim().isNotEmpty) {
      _dateQuery = parseConversationDateQuery(_query.text);
      unawaited(_run());
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Folder tiles fall back to the loaded folders when the overview cannot be read.
      final folders = context.read<FolderProvider?>();
      if (folders != null && folders.folders.isEmpty) unawaited(folders.loadFolders());
      if (widget.initialQuery == null) _focus.requestFocus();
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _query.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _loadOverview() async {
    final ApiResult<SearchOverview> result;
    try {
      result = await widget.source.overview();
    } catch (e) {
      Logger.debug('Search overview unavailable: $e');
      return;
    }
    switch (result) {
      case ApiSuccess(:final data):
        if (mounted) setState(() => _overview = data);
      case ApiFailure(:final problem):
        // Counts are decoration (an older backend has no overview route): the tiles stay, unnumbered.
        Logger.debug('Search overview unavailable: ${problem.kind}');
    }
  }

  void _onChanged(String value) {
    if (_scope?.people == true) {
      setState(() => _peopleQuery = value);
      return;
    }
    _debounce?.cancel();
    final parsed = parseConversationDateQuery(value);
    final query = value.trim();
    _generation++;
    if (query.isEmpty && _pickedStart == null) {
      setState(() {
        _dateQuery = parsed;
        _searching = false;
        _results = const _Results();
      });
      return;
    }
    setState(() {
      _dateQuery = parsed;
      _scope = null;
      _searching = true;
      _results = const _Results();
    });
    _debounce = Timer(const Duration(milliseconds: 300), () => _run());
  }

  Future<void> _run() async {
    final generation = ++_generation;
    final parsed = parseConversationDateQuery(_query.text);
    _dateQuery = parsed;
    final start = parsed.startDate ?? _pickedStart;
    final end = parsed.endDate ?? _pickedEnd;
    final hasDate = start != null;
    final query = parsed.query;
    setState(() => _searching = true);
    final source = widget.source;
    var partial = false;
    // A failed kind contributes no rows and marks the results incomplete; it is never shown as "none".
    List<T> rows<T>(ApiResult<List<T>> result) {
      switch (result) {
        case ApiSuccess(:final data):
          return data;
        case ApiFailure():
          partial = true;
          return <T>[];
      }
    }

    var conversations = const ConversationSearchResult(
        items: [], currentPage: 0, totalPages: 0, outcome: ConversationSearchResultOutcome.failure);
    var recaps = <DailySummary>[];
    var tasks = <ActionItemWithMetadata>[];
    var memories = <MemorySearchHit>[];
    // The deadline completes Future.wait, it does not cancel the source futures.
    // Mark the run settled once its results are committed so late responses
    // cannot mutate the captured locals after the UI has settled on them.
    var settled = false;
    try {
      await Future.wait<void>([
        Future.sync(() => source.conversations(query, startDate: start, endDate: end)).then((r) {
          if (!settled) conversations = r;
        }).catchError((_) {
          if (!settled) partial = true;
        }),
        Future.sync(() => hasDate ? source.recapsInRange(query, start, end ?? start) : source.recaps(query)).then((r) {
          if (settled) return;
          recaps = rows(r);
        }).catchError((_) {
          if (!settled) partial = true;
        }),
        Future.sync(() => source.tasks(query)).then((r) {
          if (settled) return;
          tasks = rows(r);
        }).catchError((_) {
          if (!settled) partial = true;
        }),
        Future.sync(() => source.memories(query)).then((r) {
          if (settled) return;
          memories = rows(r);
        }).catchError((_) {
          if (!settled) partial = true;
        }),
      ]).timeout(const Duration(seconds: 15), onTimeout: () {
        partial = true;
        return const [];
      });
    } catch (_) {
      if (!settled) partial = true;
    } finally {
      settled = true;
      if (mounted && generation == _generation) {
        if (conversations.outcome != ConversationSearchResultOutcome.success) partial = true;
        setState(() {
          _searching = false;
          _results = _Results(
            conversations: conversations.items,
            recaps: recaps,
            tasks: tasks,
            memories: memories,
            partial: partial,
          );
        });
      }
    }
  }

  Future<void> _pickDate() async {
    await showConversationDateRangePicker(
      context,
      initialStartDate: _activeStart,
      initialEndDate: _activeEnd,
      onSelected: (start, end) {
        if (!mounted) return;
        if (start.year == end.year && start.month == end.month && start.day == end.day) {
          routeToPage(context, DayConversationsPage(date: start));
          return;
        }
        _debounce?.cancel();
        _generation++;
        final remaining = parseConversationDateQuery(_query.text).query;
        _pickedStart = dayDateBounds(start).$1;
        _pickedEnd = dayDateBounds(end).$2;
        _query.text = remaining;
        _query.selection = TextSelection.collapsed(offset: remaining.length);
        _debounce?.cancel();
        _dateQuery = parseConversationDateQuery(remaining);
        setState(() {
          _scope = null;
          _searching = true;
          _results = const _Results();
        });
        unawaited(_run());
      },
      onClear: _clearDateFilter,
    );
  }

  void _clearDateFilter() {
    final remaining = _dateQuery.startDate != null ? _dateQuery.query : _query.text;
    _debounce?.cancel();
    _generation++;
    _pickedStart = null;
    _pickedEnd = null;
    _query.text = remaining;
    _query.selection = TextSelection.collapsed(offset: remaining.length);
    _debounce?.cancel();
    _dateQuery = parseConversationDateQuery(remaining);
    if (remaining.isEmpty) {
      setState(() {
        _searching = false;
        _results = const _Results();
      });
    } else {
      setState(() {
        _searching = true;
        _results = const _Results();
      });
      unawaited(_run());
    }
  }

  void _remember(String query) {
    final q = query.trim();
    if (q.isEmpty) return;
    final next = [q, ..._recent.where((r) => r.toLowerCase() != q.toLowerCase())].take(_recentSearchesMax).toList();
    _recent = next;
    SharedPreferencesUtil().saveStringList(_recentSearchesKey, next);
  }

  void _useRecent(String query) {
    _query.text = query;
    _query.selection = TextSelection.collapsed(offset: query.length);
    _onChanged(query);
  }

  Future<void> _openScope(_Scope scope) async {
    OmiHaptics.selection();
    _focus.unfocus();
    final generation = ++_generation;
    setState(() {
      _scope = scope;
      _loadingScope = true;
      _scopeConversations = const [];
    });
    final source = widget.source;
    if (scope.people) {
      // The shared PeopleProvider owns the list; tapping a person pushes the same Person page.
      _query.clear();
      _peopleQuery = '';
      final people = context.read<PeopleProvider>();
      unawaited(people.people.isEmpty ? people.initialize() : people.refresh());
      setState(() => _loadingScope = false);
      return;
    }
    final conversations = await source
        .conversationsIn(folderId: scope.folderId, starred: scope.starred)
        .catchError((_) => <ServerConversation>[]);
    if (!mounted || generation != _generation) return;
    setState(() {
      _scopeConversations = conversations;
      _loadingScope = false;
    });
  }

  /// Long-press on a folder tile: rename, recolor or delete it (the folder chips did this before).
  Future<void> _editFolder(String folderId) async {
    final folders = context.read<FolderProvider>();
    if (folders.folders.isEmpty) await folders.loadFolders();
    if (!mounted) return;
    final folder = folders.folders.where((f) => f.id == folderId).firstOrNull;
    if (folder == null) return;
    await showFolderOptions(context, folder);
    if (mounted) unawaited(_loadOverview());
  }

  void _closeScope() {
    _generation++;
    setState(() {
      if (_scope?.people == true) {
        _query.clear();
        _peopleQuery = '';
      }
      _scope = null;
      _loadingScope = false;
    });
  }

  Future<void> _openConversation(ServerConversation conversation) async {
    _remember(_query.text);
    final timestamp = conversation.startedAt ?? conversation.createdAt;
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, conversationLocalDayKey(timestamp));
    final seek = searchMomentSeekFromSnippets(snippets: conversation.matchSnippets, searchQuery: _query.text.trim());
    await routeToPage(
      context,
      ConversationDetailPage(
        conversation: conversation,
        initialTab: seek != null ? ConversationTab.transcript : null,
        initialSeekStart: seek?.start,
        initialSeekEnd: seek?.end,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Material(
      color: OmiColors.surface0,
      child: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.xs),
              child: Row(
                children: [
                  Expanded(
                    child: OmiSearchField(
                      key: const ValueKey('global_search_field'),
                      controller: _query,
                      focusNode: _focus,
                      placeholder: _scope?.people == true ? l10n.peopleSearchPlaceholder : l10n.search,
                      onChanged: _onChanged,
                      onCleared: () => _onChanged(''),
                      onSubmitted: _remember,
                    ),
                  ),
                  OmiIconButton(
                    key: const ValueKey('global_search_calendar'),
                    icon: const Icon(Icons.calendar_month_outlined),
                    label: l10n.filterByDate,
                    onPressed: _pickDate,
                  ),
                  OmiButton.tertiary(
                    key: const ValueKey('global_search_cancel'),
                    label: l10n.cancel,
                    size: OmiButtonSize.compact,
                    onPressed: () => Navigator.of(context).maybePop(),
                  ),
                ],
              ),
            ),
            if (_activeStart != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: OmiDateFilterChip(
                    key: const ValueKey('global_search_date_filter'),
                    start: _activeStart!,
                    end: _activeEnd,
                    onClear: _clearDateFilter,
                  ),
                ),
              ),
            Expanded(child: _buildBody(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    final scope = _scope;
    if (scope != null) return _buildScope(context, scope);
    if (_query.text.trim().isEmpty && _activeStart == null) return _buildBrowse(context);
    return _buildResults(context);
  }

  // ---- Before anything is typed: tiles and recent searches ----

  Widget _buildBrowse(BuildContext context) {
    final l10n = context.l10n;
    final overview = _overview;
    // The folders come from the overview when it answers, else from the ones already loaded.
    final folders = overview?.folders.isNotEmpty == true
        ? overview!.folders
        : [
            for (final f in context.watch<FolderProvider?>()?.folders ?? const [])
              SearchFolderCount(id: f.id, name: f.name, icon: f.icon, color: f.color),
          ];
    final tiles = <Widget>[
      _SearchTile(
        key: const ValueKey('search_tile_starred'),
        icon: FontAwesomeIcons.star,
        label: l10n.starred,
        count: overview?.starred,
        onTap: () => _openScope(_Scope(title: l10n.starred, starred: true)),
      ),
      for (final folder in folders)
        _SearchTile(
          key: ValueKey('search_tile_folder_${folder.id}'),
          icon: folderIconToFa(folder.icon),
          iconColor: _hexColor(folder.color),
          label: folder.name,
          count: folder.count,
          onTap: () => _openScope(_Scope(title: folder.name, folderId: folder.id)),
          onLongPress: () => _editFolder(folder.id),
        ),
      _SearchTile(
        key: const ValueKey('search_tile_recaps'),
        icon: FontAwesomeIcons.calendarDay,
        label: l10n.recaps,
        count: overview?.recaps,
        onTap: () => routeToPage(context, const DailyRecapsPage()),
      ),
      _SearchTile(
        key: const ValueKey('search_tile_memories'),
        icon: FontAwesomeIcons.brain,
        label: l10n.memories,
        count: overview?.memories,
        onTap: () => routeToPage(context, const MemoriesPage()),
      ),
      _SearchTile(
        key: const ValueKey('search_tile_people'),
        icon: FontAwesomeIcons.userGroup,
        label: l10n.people,
        count: overview?.people,
        onTap: () => _openScope(_Scope(title: l10n.people, people: true)),
      ),
      _SearchTile(
        key: const ValueKey('search_tile_places'),
        icon: FontAwesomeIcons.locationDot,
        label: l10n.places,
        count: overview?.places,
        onTap: () {
          final conversations = context.read<ConversationProvider>().displayedConversations;
          routeToPage(context, ConversationMapPage(conversations: conversations));
        },
      ),
      _SearchTile(
        key: const ValueKey('search_tile_new_folder'),
        icon: FontAwesomeIcons.plus,
        label: l10n.newFolder,
        onTap: () async {
          OmiHaptics.selection();
          if (await showCreateFolderBottomSheet(context)) unawaited(_loadOverview());
        },
      ),
    ];
    return ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      padding:
          EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, MediaQuery.paddingOf(context).bottom + 24),
      children: [
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: OmiSpacing.xs,
          crossAxisSpacing: OmiSpacing.xs,
          childAspectRatio: 1.9,
          children: tiles,
        ),
        if (_recent.isNotEmpty) ...[
          _SectionLabel(l10n.recent),
          for (final query in _recent)
            _Row(
              leading: Icon(Icons.history_rounded, size: 18, color: OmiColors.textTertiary),
              title: query,
              onTap: () => _useRecent(query),
            ),
        ],
      ],
    );
  }

  // ---- Typed: grouped results ----

  Widget _buildResults(BuildContext context) {
    final l10n = context.l10n;
    final r = _results;
    if (_searching && r.isEmpty) {
      return const Center(child: OmiSpinner());
    }
    if (r.isEmpty && r.partial) {
      return OmiErrorState(message: l10n.searchPartialFailure, onRetry: _run);
    }
    if (r.isEmpty) {
      return OmiEmptyState(icon: Icons.search_off_rounded, title: l10n.noResultsFound);
    }
    final dates = OmiDateFormat.of(context);
    return ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + 24),
      children: [
        if (_searching) const LinearProgressIndicator(minHeight: 1),
        if (r.partial) OmiPartialNotice(onRetry: _run),
        if (r.recaps.isNotEmpty) ...[
          _SectionLabel(l10n.recaps),
          for (final recap in r.recaps)
            _Row(
              leading: _Emoji(recap.dayEmoji),
              title: recap.headline,
              subtitle: '${recapDateLabel(context, recap.date)} · ${recap.overview}',
              onTap: () {
                _remember(_query.text);
                routeToPage(context, DailySummaryDetailPage(summaryId: recap.id, summary: recap));
              },
            ),
        ],
        if (r.conversations.isNotEmpty) ...[
          _SectionLabel(l10n.conversations),
          for (final conversation in r.conversations)
            _Row(
              key: ValueKey('search_conversation_${conversation.id}'),
              leading: _Emoji(conversation.structured.emoji),
              title: conversation.structured.title,
              subtitle: [
                dates.timestamp(conversation.startedAt ?? conversation.createdAt),
                if (conversation.matchSnippets.isNotEmpty) conversation.matchSnippets.first.text,
              ].join(' · '),
              onTap: () => _openConversation(conversation),
            ),
        ],
        if (r.tasks.isNotEmpty) ...[
          _SectionLabel(l10n.tasks),
          for (final task in r.tasks)
            _Row(
              leading: Icon(
                task.completed ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
                size: 18,
                color: OmiColors.textTertiary,
              ),
              title: task.description,
              onTap: () {
                _remember(_query.text);
                showActionItemFormSheet(context, actionItem: task);
              },
            ),
        ],
        if (r.memories.isNotEmpty) ...[
          _SectionLabel(l10n.memories),
          for (final memory in r.memories)
            _Row(
              leading: FaIcon(FontAwesomeIcons.brain, size: 14, color: OmiColors.textTertiary),
              title: memory.content,
              maxTitleLines: 2,
              onTap: () {
                _remember(_searchedQuery);
                context.read<MemoriesProvider>().setSearchQuery(_searchedQuery);
                routeToPage(context, const MemoriesPage());
              },
            ),
        ],
      ],
    );
  }

  // ---- A browsed list: a folder, Starred, the people, or one person ----

  Widget _buildScope(BuildContext context, _Scope scope) {
    final dates = OmiDateFormat.of(context);
    final Widget body;
    if (_loadingScope) {
      body = const Center(child: OmiSpinner());
    } else if (scope.people) {
      // The shared list without management chrome: no Select, Add or Clean Up. Rows still swipe to
      // pin or delete and long-press for the row menu.
      body = PeopleList(
        key: const ValueKey('search_people_list'),
        query: _peopleQuery,
        onClearQuery: () => _useRecent(''),
      );
    } else {
      body = _scopeConversations.isEmpty
          ? OmiEmptyState(icon: Icons.forum_outlined, title: context.l10n.noConversationsYet)
          : ListView(
              padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + 24),
              children: [
                for (final conversation in _scopeConversations)
                  _Row(
                    leading: _Emoji(conversation.structured.emoji),
                    title: conversation.structured.title,
                    subtitle: dates.timestamp(conversation.startedAt ?? conversation.createdAt),
                    onTap: () => _openConversation(conversation),
                  ),
              ],
            );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.md, OmiSpacing.xxs),
          child: Row(
            children: [
              OmiBackButton(onPressed: _closeScope, color: OmiColors.textPrimary),
              Expanded(
                child: Text(scope.title, style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ],
          ),
        ),
        Expanded(child: body),
      ],
    );
  }
}

Color? _hexColor(String hex) {
  final value = int.tryParse(hex.replaceFirst('#', ''), radix: 16);
  if (value == null) return null;
  return Color(hex.length <= 7 ? 0xFF000000 | value : value);
}

/// A browse tile: glyph, count, and a one-word label. No count when the server could not count.
class _SearchTile extends StatelessWidget {
  const _SearchTile({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.onLongPress,
    this.count,
    this.iconColor,
  });

  final FaIconData icon;
  final String label;
  final int? count;
  final Color? iconColor;
  final VoidCallback onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: count == null ? label : '$label, $count',
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        onLongPress: onLongPress,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  FaIcon(icon, size: 17, color: iconColor ?? OmiColors.textPrimary),
                  const Spacer(),
                  if (count != null) Text('$count', style: OmiType.title3),
                ],
              ),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.xxs),
      child: Semantics(
        header: true,
        child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
      ),
    );
  }
}

class _Emoji extends StatelessWidget {
  const _Emoji(this.emoji);

  final String emoji;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 30,
      height: 30,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
      child: Text(emoji.isEmpty ? '·' : emoji, style: OmiType.subhead),
    );
  }
}

/// One result row: a leading glyph, a title, and an optional one-line subtitle.
class _Row extends StatelessWidget {
  const _Row({
    super.key,
    required this.leading,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.maxTitleLines = 1,
  });

  final Widget leading;
  final String title;
  final String? subtitle;
  final int maxTitleLines;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 10),
            child: Row(
              children: [
                SizedBox(width: 30, child: Center(child: leading)),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, maxLines: maxTitleLines, overflow: TextOverflow.ellipsis, style: OmiType.subhead),
                      if (subtitle != null && subtitle!.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            subtitle!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                          ),
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
