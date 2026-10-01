import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/utils/logger.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversation_map_page.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/pages/conversations/widgets/folder_options_sheet.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

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
class SearchDropRoute<T> extends PageRoute<T> {
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
      builder(context);

  @override
  Widget buildTransitions(
      BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation, Widget child) {
    return SearchDropTransition(animation: animation, child: child);
  }
}

/// The drop itself, separate from the route so tests and the visual audit can pump one frame of it.
class SearchDropTransition extends StatelessWidget {
  const SearchDropTransition({super.key, required this.animation, required this.child});

  final Animation<double> animation;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final drop = CurvedAnimation(parent: animation, curve: kSearchDropCurve, reverseCurve: Curves.easeInCubic);
    final dim = CurvedAnimation(parent: animation, curve: Curves.easeOut);
    return Stack(
      fit: StackFit.expand,
      children: [
        IgnorePointer(
          child: FadeTransition(opacity: dim, child: ColoredBox(color: Colors.black.withValues(alpha: 0.18))),
        ),
        SlideTransition(
          position: Tween<Offset>(begin: const Offset(0, -1), end: Offset.zero).animate(drop),
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
  Future<ConversationSearchResult> conversations(String query, {String? speakerId});
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false});
  Future<ApiResult<List<DailySummary>>> recaps(String query);
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query);
  Future<ApiResult<List<MemorySearchHit>>> memories(String query);
}

class ApiGlobalSearchSource extends GlobalSearchSource {
  const ApiGlobalSearchSource();

  @override
  Future<ApiResult<SearchOverview>> overview() => getSearchOverview();

  @override
  Future<ConversationSearchResult> conversations(String query, {String? speakerId}) =>
      searchConversationsServerResult(query, limit: 20, includeDiscarded: false, speakerId: speakerId);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) =>
      getConversations(limit: 50, folderId: folderId, starred: starred ? true : null);

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) => searchDailySummaries(query);

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

  @override
  void initState() {
    super.initState();
    _recent = SharedPreferencesUtil().getStringList(_recentSearchesKey);
    unawaited(_loadOverview());
    if (_query.text.trim().isNotEmpty) unawaited(_run(_query.text.trim()));
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
    switch (await widget.source.overview()) {
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
    final query = value.trim();
    if (query.isEmpty) {
      _generation++;
      setState(() {
        _searching = false;
        _results = const _Results();
      });
      return;
    }
    setState(() => _scope = null);
    _debounce = Timer(const Duration(milliseconds: 300), () => _run(query));
  }

  Future<void> _run(String query) async {
    final generation = ++_generation;
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

    final (conversations, recaps, tasks, memories) = await (
      source.conversations(query),
      source.recaps(query),
      source.tasks(query),
      source.memories(query),
    ).wait;
    if (!mounted || generation != _generation) return;
    if (conversations.outcome != ConversationSearchResultOutcome.success) partial = true;
    setState(() {
      _searching = false;
      _results = _Results(
        conversations: conversations.items,
        recaps: rows(recaps),
        tasks: rows(tasks),
        memories: rows(memories),
        partial: partial,
      );
    });
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
        initialTabIndex: seek != null ? 0 : null,
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
                  OmiButton.tertiary(
                    key: const ValueKey('global_search_cancel'),
                    label: l10n.cancel,
                    size: OmiButtonSize.compact,
                    onPressed: () => Navigator.of(context).maybePop(),
                  ),
                ],
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
    if (_query.text.trim().isEmpty) return _buildBrowse(context);
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
      return OmiErrorState(message: l10n.searchPartialFailure, onRetry: () => _run(_query.text.trim()));
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
        if (r.partial) _PartialNotice(onRetry: () => _run(_query.text.trim())),
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
                _remember(_query.text);
                context.read<MemoriesProvider>().setSearchQuery(_query.text.trim());
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

/// A quiet line above incomplete results: one kind failed to load; retry runs the search again.
class _PartialNotice extends StatelessWidget {
  const _PartialNotice({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
        child: Row(
          children: [
            Icon(Icons.error_outline_rounded, size: 16, color: OmiColors.textTertiary),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(
              child: Text(l10n.searchPartialFailure, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ),
            OmiButton.secondary(
              key: const ValueKey('search_partial_retry'),
              label: l10n.tryAgain,
              size: OmiButtonSize.compact,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}
