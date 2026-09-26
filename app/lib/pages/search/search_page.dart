import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/capture_sources.dart';

/// What a search looks through.
enum SearchScope { all, conversations, memories, tasks }

/// Looks up conversations for a query (the server's conversation search; injectable for tests).
typedef SearchConversations = Future<List<ServerConversation>> Function(String query);

Future<List<ServerConversation>> _serverConversations(String query) async {
  final result = await searchConversationsServerResult(query, page: 1, limit: 20, includeDiscarded: false);
  return result.isSuccess ? result.items : const [];
}

/// Search everything (canvas "Search everything"), from the Search button on Today: one field over
/// conversations (the server's search, which also matches what was said), memories and to-dos, with
/// scope chips, the last few searches, and Ask Omi when words are not enough.
class SearchPage extends StatefulWidget {
  const SearchPage({super.key, this.searchConversations});

  /// Defaults to the server's conversation search.
  final SearchConversations? searchConversations;

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  static const _recentKey = 'v2/recentSearches';
  static const _recentLimit = 5;

  final _controller = TextEditingController();
  final _focus = FocusNode();
  Timer? _debounce;
  SearchScope _scope = SearchScope.all;
  String _query = '';
  bool _loading = false;
  List<ServerConversation> _conversations = const [];
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _focus.requestFocus();
      // Memories and to-dos are searched where they are already loaded; load them if not yet.
      final memories = context.read<MemoriesProvider>();
      if (memories.memories.isEmpty) unawaited(memories.init());
      final tasks = context.read<ActionItemsProvider>();
      if (tasks.actionItems.isEmpty) unawaited(tasks.refreshActionItems());
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  List<String> get _recent => SharedPreferencesUtil().getStringList(_recentKey);

  void _remember(String query) {
    final q = query.trim();
    if (q.isEmpty) return;
    final next = [q, ..._recent.where((r) => r.toLowerCase() != q.toLowerCase())].take(_recentLimit).toList();
    SharedPreferencesUtil().saveStringList(_recentKey, next);
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    setState(() => _query = value.trim());
    if (_query.isEmpty) {
      setState(() {
        _conversations = const [];
        _loading = false;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () => _search(_query));
  }

  Future<void> _search(String query) async {
    final generation = ++_generation;
    setState(() => _loading = true);
    final found = await (widget.searchConversations ?? _serverConversations)(query);
    if (!mounted || generation != _generation) return;
    setState(() {
      _conversations = found;
      _loading = false;
    });
  }

  void _useQuery(String query) {
    _controller.text = query;
    _controller.selection = TextSelection.collapsed(offset: query.length);
    _onChanged(query);
  }

  void _ask(String question) {
    OmiHaptics.selection();
    if (question.trim().isNotEmpty) _remember(_query);
    routeToPage(context, ChatPage(isPivotBottom: false, initialQuestion: question));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      key: const ValueKey('search_page'),
      backgroundColor: OmiColors.surface0,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
              child: Row(
                children: [
                  Expanded(child: _field(context)),
                  const SizedBox(width: 10),
                  Semantics(
                    button: true,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => Navigator.of(context).maybePop(),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(minHeight: OmiSize.minTap),
                        child: Center(
                          child: Text(l10n.cancel, style: OmiType.body.copyWith(fontWeight: FontWeight.w500)),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, 40),
                children: [
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (final scope in SearchScope.values) ...[
                          OmiChip(
                            key: ValueKey('search_scope_${scope.name}'),
                            label: switch (scope) {
                              SearchScope.all => l10n.all,
                              SearchScope.conversations => l10n.conversations,
                              SearchScope.memories => l10n.memories,
                              SearchScope.tasks => l10n.tasks,
                            },
                            selected: _scope == scope,
                            onTap: () {
                              OmiHaptics.selection();
                              setState(() => _scope = scope);
                            },
                          ),
                          const SizedBox(width: OmiSpacing.xs),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  if (_query.isEmpty) ..._idle(context) else ..._results(context),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field(BuildContext context) {
    final l10n = context.l10n;
    return OmiGlass(
      borderRadius: OmiRadius.pillAll,
      child: SizedBox(
        height: OmiSize.minTap,
        child: Row(
          children: [
            const SizedBox(width: 12),
            OmiGlyph(OmiGlyphs.magnifyingGlass, size: 18, color: OmiColors.textSecondary),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(
              child: TextField(
                key: const ValueKey('search_field'),
                controller: _controller,
                focusNode: _focus,
                onChanged: _onChanged,
                onSubmitted: (value) => _remember(value),
                textInputAction: TextInputAction.search,
                style: OmiType.body,
                cursorColor: OmiColors.textPrimary,
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: l10n.searchEverything,
                  hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
                ),
              ),
            ),
            if (_query.isNotEmpty)
              OmiIconButton(
                icon: Icon(Icons.cancel_rounded, size: 18, color: OmiColors.textTertiary),
                label: l10n.clear,
                onPressed: () => _useQuery(''),
              )
            else
              const SizedBox(width: 12),
          ],
        ),
      ),
    );
  }

  List<Widget> _idle(BuildContext context) {
    final l10n = context.l10n;
    final recent = _recent;
    return [
      if (recent.isNotEmpty) ...[
        OmiSettingsGroup(
          header: l10n.recentSearches,
          children: [
            for (final term in recent)
              OmiSettingsRow(
                key: ValueKey('search_recent_$term'),
                leading: Icon(Icons.history_rounded, color: OmiColors.textSecondary),
                title: term,
                showChevron: false,
                onTap: () => _useQuery(term),
              ),
          ],
        ),
        const SizedBox(height: 22),
      ],
      OmiSettingsGroup(
        header: l10n.askOmi,
        children: [
          OmiSettingsRow(
            key: const ValueKey('search_ask_suggestion'),
            leading: const OmiRingLogo(size: 20),
            title: l10n.searchAskSuggestion,
            onTap: () => _ask(l10n.searchAskSuggestion),
          ),
        ],
      ),
    ];
  }

  List<Widget> _results(BuildContext context) {
    final l10n = context.l10n;
    final q = _query.toLowerCase();
    final rows = <_Result>[];
    if (_scope == SearchScope.all || _scope == SearchScope.conversations) {
      for (final c in _conversations) {
        rows.add(_Result.conversation(context, c));
      }
    }
    if (_scope == SearchScope.all || _scope == SearchScope.memories) {
      for (final m in context.watch<MemoriesProvider>().memories) {
        if (!m.deleted && m.content.toLowerCase().contains(q)) rows.add(_Result.memory(context, m));
      }
    }
    if (_scope == SearchScope.all || _scope == SearchScope.tasks) {
      for (final t in context.watch<ActionItemsProvider>().actionItems) {
        if (t.description.toLowerCase().contains(q)) rows.add(_Result.task(context, t));
      }
    }
    if (rows.isEmpty && _loading) {
      return [const Padding(padding: EdgeInsets.only(top: 40), child: Center(child: OmiSpinner()))];
    }
    if (rows.isEmpty) {
      return [
        Padding(
          key: const ValueKey('search_nothing_found'),
          padding: const EdgeInsets.fromLTRB(20, 40, 20, 0),
          child: Column(
            children: [
              OmiGlyph(OmiGlyphs.magnifyingGlass, size: 30, color: OmiColors.textTertiary),
              const SizedBox(height: 12),
              Text(l10n.nothingFound, style: OmiType.headline, textAlign: TextAlign.center),
              const SizedBox(height: 6),
              Text(
                l10n.searchNothingFoundHint,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              OmiChip(
                key: const ValueKey('search_ask_instead'),
                label: l10n.askOmiInstead,
                leading: const OmiRingLogo(size: 14),
                selected: false,
                onTap: () => _ask(_query),
              ),
            ],
          ),
        ),
      ];
    }
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 10),
        child: Text(
          l10n.searchResultsCount(rows.length),
          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
        ),
      ),
      OmiCard(
        clip: true,
        child: Column(
          children: [
            for (final (i, row) in rows.indexed) ...[
              if (i > 0) Divider(height: 0.5, thickness: 0.5, indent: 60, color: OmiColors.border),
              _ResultTile(
                result: row,
                query: _query,
                onTap: () {
                  _remember(_query);
                  row.open(context);
                },
              ),
            ],
          ],
        ),
      ),
    ];
  }
}

/// One search hit, whatever it is.
class _Result {
  _Result({required this.glyph, required this.title, required this.meta, required this.open, this.snippet});

  factory _Result.conversation(BuildContext context, ServerConversation c) {
    final l10n = context.l10n;
    final source = c.source?.name;
    final title = c.structured.title.trim().isEmpty ? l10n.untitledConversation : c.structured.title.trim();
    final overview = OmiPlainText.fromMarkdown(c.structured.overview);
    return _Result(
      glyph: OmiGlyphs.bubbles,
      title: title,
      snippet: overview.isEmpty ? null : overview,
      meta: [
        OmiDateFormat.of(context).timestamp(c.createdAt),
        if (source != null) CaptureSources.label(context, source),
      ].join(' · '),
      open: (context) => openChatBlockConversation(context, conversationId: c.id),
    );
  }

  factory _Result.memory(BuildContext context, Memory m) => _Result(
        glyph: OmiGlyphs.graph,
        title: m.content,
        meta: '${context.l10n.memories} · ${OmiDateFormat.of(context).timestamp(m.createdAt)}',
        open: (context) => showMemoryQuickEditSheet(context, m, context.read<MemoriesProvider>()),
      );

  factory _Result.task(BuildContext context, ActionItemWithMetadata t) => _Result(
        glyph: OmiGlyphs.checklist,
        title: t.description,
        meta: context.l10n.tasks,
        open: (context) => showActionItemFormSheet(context, actionItem: t),
      );

  final String glyph;
  final String title;
  final String? snippet;
  final String meta;
  final Future<Object?> Function(BuildContext context) open;
}

class _ResultTile extends StatelessWidget {
  const _ResultTile({required this.result, required this.query, required this.onTap});

  final _Result result;
  final String query;
  final VoidCallback onTap;

  /// [text] with the first match of [query] in bold primary, the rest in secondary (canvas).
  TextSpan _highlight(String text) {
    final base = OmiType.body.copyWith(color: OmiColors.textSecondary);
    final at = query.isEmpty ? -1 : text.toLowerCase().indexOf(query.toLowerCase());
    if (at < 0) return TextSpan(text: text, style: base.copyWith(color: OmiColors.textPrimary));
    return TextSpan(
      style: base,
      children: [
        TextSpan(text: text.substring(0, at)),
        TextSpan(
          text: text.substring(at, at + query.length),
          style: TextStyle(color: OmiColors.textPrimary, fontWeight: FontWeight.w700),
        ),
        TextSpan(text: text.substring(at + query.length)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      type: MaterialType.transparency,
      child: InkWell(
        onTap: onTap,
        splashFactory: NoSplash.splashFactory,
        highlightColor: OmiColors.cellPressed,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 13),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              OmiIconTile(size: 32, child: OmiGlyph(result.glyph, size: 18)),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text.rich(_highlight(result.title), maxLines: 2, overflow: TextOverflow.ellipsis),
                    if (result.snippet != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        result.snippet!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                    const SizedBox(height: 2),
                    Text(result.meta, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
