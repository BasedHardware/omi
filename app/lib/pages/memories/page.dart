import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_graph.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'widgets/memory_dialog.dart';
import 'widgets/memory_edit_sheet.dart';
import 'widgets/memory_graph_controller.dart';
import 'widgets/memory_graph_native.dart';
import 'widgets/memory_graph_page.dart';
import 'widgets/memory_history_status_banner.dart';
import 'widgets/memory_item.dart';
import 'widgets/memory_management_sheet.dart';
import 'widgets/memories_load_error.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage(
      {super.key, this.asRoot = false, this.showMindMap = true, this.loadGraph = KnowledgeGraphApi.getKnowledgeGraph});
  final bool asRoot;

  /// The live graph preview at the top. The graph needs a real canvas and network, so harnesses
  /// that pump the page without them turn it off.
  final bool showMindMap;

  /// Where the graph preview loads from; harnesses pass a fixture.
  @visibleForTesting
  final Future<Map<String, dynamic>> Function() loadGraph;

  @override
  State<MemoriesPage> createState() => MemoriesPageState();
}

class MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  bool _isInitialLoad = true;
  String? _highlightedMemoryId;
  Timer? _highlightTimer;

  /// The native mind map card's graph; the classic card owns its own.
  MemoryGraphController? _graph;
  Future<void>? _graphSupport;

  Future<void> _createMemory(MemoriesProvider provider) async {
    final existingIds = provider.memories.map((m) => m.id).toSet();
    final saved = await showMemoryDialog(context, provider);
    if (!mounted || saved != true) return;
    final added = provider.memories.where((m) => !existingIds.contains(m.id));
    if (added.isEmpty) return;
    _highlightTimer?.cancel();
    setState(() => _highlightedMemoryId = added.last.id);
    _highlightTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => _highlightedMemoryId = null);
    });
  }

  @override
  void dispose() {
    if (nativePresentationEnabled) WidgetsBinding.instance.removeObserver(this);
    _graph
      ?..removeListener(_onGraphChanged)
      ..dispose();
    _graph = null;
    _highlightTimer?.cancel();
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    if (nativePresentationEnabled) WidgetsBinding.instance.addObserver(this);
    (() async {
      final provider = context.read<MemoriesProvider>();
      try {
        await provider.init();
      } finally {
        // Always leave the initial-load state, even if init() threw. Otherwise
        // `provider.loading && _isInitialLoad` stays true and the page is stuck
        // on the loading skeleton forever.
        if (mounted) {
          setState(() {
            _isInitialLoad = false;
          });
        }
      }
    }).withPostFrameCallback();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The card reloads quietly on resume, as the classic card does.
    if (state == AppLifecycleState.resumed) _graph?.load(silent: true);
  }

  Widget _buildHeader(MemoriesProvider provider, {required bool loading}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 10),
      child: Row(
        children: [
          Expanded(
            child: Consumer<HomeProvider>(
              builder: (context, home, child) => OmiSearchField(
                placeholder: context.l10n.searchMemories,
                controller: _searchController,
                focusNode: loading ? null : home.memoriesSearchFieldFocusNode,
                onChanged: provider.setSearchQuery,
                onCleared: () => PlatformManager.instance.analytics.memorySearchCleared(provider.memories.length),
                onSubmitted: (value) {
                  if (value.isNotEmpty) {
                    PlatformManager.instance.analytics.memorySearched(value, provider.filteredMemories.length);
                  }
                },
              ),
            ),
          ),
          const SizedBox(width: OmiSpacing.xxs),
          OmiIconButton.filled(
            icon: const FaIcon(FontAwesomeIcons.sliders, size: 16),
            label: context.l10n.memoryManagement,
            diameter: 40,
            onPressed: loading ? null : () => _showMemoryManagementSheet(context, provider),
          ),
        ],
      ),
    );
  }

  /// The account has no memories at all (not a search or filter with no matches).
  bool _showsFirstMemoryAction(MemoriesProvider provider) =>
      !(provider.loading && _isInitialLoad) &&
      !provider.showLoadError &&
      provider.memories.isEmpty &&
      provider.searchQuery.isEmpty &&
      !provider.filterThisDeviceOnly;

  Widget _buildEmptyState(MemoriesProvider provider) {
    final l10n = context.l10n;
    final searching = provider.searchQuery.isNotEmpty;
    final filtered = provider.memories.isNotEmpty || provider.filterThisDeviceOnly;
    return KeyedSubtree(
      key: const Key('memories_empty_state'),
      child: OmiEmptyState(
        icon: searching ? Icons.search_off_rounded : Icons.psychology_outlined,
        title: searching
            ? l10n.noMemoriesFound
            : filtered
                ? l10n.noMemoriesInCategories
                : l10n.noMemoriesYet,
        action: OmiButton(
          key: const Key('memories_empty_action'),
          variant: searching || filtered ? OmiButtonVariant.secondary : OmiButtonVariant.primary,
          size: OmiButtonSize.compact,
          label: searching
              ? l10n.clearSearch
              : filtered
                  ? l10n.resetFilters
                  : l10n.addFirstMemory,
          onPressed: () {
            if (searching) {
              _searchController.clear();
              provider.setSearchQuery('');
            } else if (filtered) {
              provider.clearCategoryFilter();
              provider.setFilterThisDeviceOnly(false);
              provider.setCollectionView(MemoryCollectionView.all);
            } else {
              _createMemory(provider);
            }
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final classic = Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: AppBar(
              automaticallyImplyLeading: !widget.asRoot,
              leading: widget.asRoot ? null : const OmiBackButton(),
              title: Text(context.l10n.memories)),
          body: Stack(
            children: [
              RefreshIndicator(
                onRefresh: () async {
                  OmiHaptics.medium();
                  await provider.init();
                },
                child: provider.loading && _isInitialLoad
                    ? CustomScrollView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        slivers: [
                          SliverToBoxAdapter(child: _buildHeader(provider, loading: true)),
                          SliverFillRemaining(child: _buildShimmerMemoryList()),
                        ],
                      )
                    : CustomScrollView(
                        controller: _scrollController,
                        physics: const AlwaysScrollableScrollPhysics(),
                        slivers: [
                          // The mind map leads the page (it moved here from Home); tap to expand.
                          if (widget.showMindMap && provider.searchQuery.isEmpty && provider.memories.isNotEmpty)
                            SliverToBoxAdapter(child: MemoryMindMapPreview(loadGraph: widget.loadGraph)),
                          SliverToBoxAdapter(child: _buildHeader(provider, loading: false)),
                          if (provider.showPartialLoadError)
                            SliverToBoxAdapter(
                              child: MemoriesPartialLoadBanner(onRetry: () => provider.loadMemories()),
                            ),
                          if (provider.memoryBeliefEnabled &&
                              provider.showHistory &&
                              (provider.ledgerHistoryTruncated || provider.ledgerHistoryHasMore))
                            SliverToBoxAdapter(
                              child: Padding(
                                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                                child: MemoryHistoryStatusBanner(
                                  onLoadMore: provider.ledgerHistoryHasMore ? provider.loadMoreHistory : null,
                                ),
                              ),
                            ),
                          if (provider.showLoadError || provider.filteredMemories.isEmpty)
                            SliverFillRemaining(
                              hasScrollBody: false,
                              child: MemoriesEmptyOrError(
                                showLoadError: provider.showLoadError,
                                onRetry: () => provider.loadMemories(),
                                emptyState: _buildEmptyState(provider),
                              ),
                            )
                          else
                            SliverPadding(
                              padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 120),
                              sliver: SliverList(
                                delegate: SliverChildBuilderDelegate((context, index) {
                                  final memory = provider.filteredMemories[index];
                                  return MemoryItem(
                                    memory: memory,
                                    highlighted: memory.id == _highlightedMemoryId,
                                    provider: provider,
                                    onTap:
                                        (BuildContext context, Memory tappedMemory, MemoriesProvider tappedProvider) {
                                      PlatformManager.instance.analytics.memoryListItemClicked(tappedMemory);
                                      _showQuickEditSheet(context, tappedMemory, tappedProvider);
                                    },
                                  );
                                }, childCount: provider.filteredMemories.length),
                              ),
                            ),
                        ],
                      ),
              ),
              // The empty state's "Add your first memory" is how the page gets its first row (ux-contract
              // §13: one action), so the add button joins once there is a memory.
              if (!_showsFirstMemoryAction(provider))
                Positioned(
                  right: 20,
                  bottom: 100,
                  // One named node: FloatingActionButton's tooltip names a wrapper, not the button.
                  child: Semantics(
                    button: true,
                    label: context.l10n.createMemoryTooltip,
                    excludeSemantics: true,
                    onTap: () => _createMemory(provider),
                    child: FloatingActionButton(
                      heroTag: 'memories_fab',
                      onPressed: () {
                        _createMemory(provider);
                        PlatformManager.instance.analytics.memoriesPageCreateMemoryBtn();
                      },
                      backgroundColor: OmiColors.accent,
                      foregroundColor: OmiColors.onAccent,
                      child: const Icon(Icons.add),
                    ),
                  ),
                ),
            ],
          ),
        );
        if (!nativePresentationEnabled) return classic;
        return _buildNative(context, provider, classic);
      },
    );
  }

  /// The Memories list as one native surface over the same provider and handlers.
  Widget _buildNative(BuildContext context, MemoriesProvider provider, Widget classic) {
    final l10n = context.l10n;
    final loading = provider.loading && _isInitialLoad;
    final searching = provider.searchQuery.isNotEmpty;
    final filtered = provider.memories.isNotEmpty || provider.filterThisDeviceOnly;
    final showGraph = widget.showMindMap && !searching && provider.memories.isNotEmpty;
    // Locked rows name the upgrade only where the plan page offers one.
    context.watch<UsageProvider>();
    void onEdit(BuildContext context, Memory memory, MemoriesProvider provider) {
      PlatformManager.instance.analytics.memoryListItemClicked(memory);
      _showQuickEditSheet(context, memory, provider);
    }

    return IosNativeSurface(
        title: l10n.memories,
        fallback: classic,
        loading: loading,
        failed: provider.showLoadError,
        errorMessage: l10n.couldNotLoadMemories,
        empty: searching ? l10n.noMemoriesFound : l10n.noMemoriesYet,
        searchValue: provider.searchQuery,
        searchPlaceholder: l10n.searchMemories,
        search: (value) => _onNativeSearch(provider, value as String),
        onRefresh: (_) => provider.init(),
        toolbar: [
          if (!widget.asRoot)
            NativeRow('memories_back', l10n.back, symbol: 'chevron.left', action: (_) {
              Navigator.of(context).pop();
            }),
          if (!_showsFirstMemoryAction(provider))
            NativeRow('memories_add', l10n.createMemoryTooltip, symbol: 'plus', action: (_) {
              _createMemory(provider);
              PlatformManager.instance.analytics.memoriesPageCreateMemoryBtn();
            }),
          NativeRow('memories_manage', l10n.memoryManagement, symbol: 'line.3.horizontal.decrease', enabled: !loading,
              action: (_) {
            _showMemoryManagementSheet(context, provider);
          }),
        ],
        sections: [
          if (showGraph) NativeSection('memory_graph', _graphPreviewRows(context)),
          if (provider.showPartialLoadError)
            NativeSection('memory_partial', [
              NativeRow('memory_partial_label', l10n.couldNotLoadMemories, kind: 'label'),
              NativeRow('memory_partial_retry', l10n.tryAgain, action: (_) => provider.loadMemories()),
            ]),
          if (provider.memoryBeliefEnabled &&
              provider.showHistory &&
              (provider.ledgerHistoryTruncated || provider.ledgerHistoryHasMore))
            NativeSection('memory_history', [
              NativeRow('memory_history_label', l10n.memoryHistoryPartial, kind: 'label'),
              if (provider.ledgerHistoryHasMore)
                NativeRow('memory_history_more', l10n.showMore, action: (_) => provider.loadMoreHistory()),
            ]),
          NativeSection('memories', [
            for (final memory in provider.filteredMemories) memoryNativeRow(context, memory, provider, onEdit: onEdit),
          ]),
          // The Flutter empty state and its one action: clear the search, reset the filters, or add
          // the first memory.
          if (!loading && !provider.showLoadError && provider.filteredMemories.isEmpty)
            NativeSection('memory_empty', [
              NativeRow(
                  'memory_empty_label',
                  searching
                      ? l10n.noMemoriesFound
                      : filtered
                          ? l10n.noMemoriesInCategories
                          : l10n.noMemoriesYet,
                  kind: 'label'),
              if (searching)
                NativeRow('memory_clear_search', l10n.clearSearch, action: (_) {
                  // As the classic empty state: no search-cleared event, which only the field's clear sends.
                  _searchController.clear();
                  provider.setSearchQuery('');
                })
              else if (filtered)
                NativeRow('memory_reset_filters', l10n.resetFilters, action: (_) {
                  provider.clearCategoryFilter();
                  provider.setFilterThisDeviceOnly(false);
                  provider.setCollectionView(MemoryCollectionView.all);
                })
              else
                NativeRow('memory_add_first', l10n.addFirstMemory, action: (_) => _createMemory(provider)),
            ]),
        ]);
  }

  /// Native search keeps the classic field and its analytics in step: clearing a query reports the
  /// clear as the field's clear button does. The bridge has no submit event (see the batch report).
  void _onNativeSearch(MemoriesProvider provider, String value) {
    final cleared = value.isEmpty && provider.searchQuery.isNotEmpty;
    if (_searchController.text != value) _searchController.text = value;
    provider.setSearchQuery(value);
    if (cleared) PlatformManager.instance.analytics.memorySearchCleared(provider.memories.length);
  }

  /// Starts the card's own graph owner once the native renderer is confirmed, so an unsupported
  /// system (which shows the classic card with its own graph) never loads the graph twice.
  void _startGraphPreview() {
    _graphSupport ??= supportsNativePresentation().then((supported) {
      if (!supported || !mounted || _graph != null) return;
      final controller = MemoryGraphController(loadGraph: widget.loadGraph, localizations: () => context.l10n)
        ..addListener(_onGraphChanged);
      _graph = controller;
      controller.load();
    }, onError: (_) {});
  }

  void _onGraphChanged() {
    if (mounted) setState(() {});
  }

  void _openGraph(Object? _) =>
      routeToPage(context, MemoryGraphPage(trackOpenEvent: false, loadGraph: widget.loadGraph));

  /// The mind map card: a placeholder while loading, the zoomed-out graph once loaded, two lines
  /// for an empty graph and one Try Again on failure. A graph the native renderer cannot take
  /// becomes a plain row, so the list itself never falls back because of the graph.
  List<NativeRow> _graphPreviewRows(BuildContext context) {
    final l10n = context.l10n;
    final graph = _graph;
    if (graph == null || graph.isLoading) {
      if (graph == null) _startGraphPreview();
      return [
        NativeRow('memory_graph_preview', l10n.memoryGraph,
            kind: 'graph',
            graph: NativeGraph.placeholder(layout: 'card', height: 140, accent: memoryGraphAccentHex()),
            action: _openGraph),
      ];
    }
    final error = graph.error;
    if (error != null) {
      return [
        NativeRow('memory_graph_error', error, kind: 'label'),
        NativeRow('memory_graph_retry', l10n.tryAgain, symbol: 'arrow.clockwise', action: (_) => graph.load()),
      ];
    }
    if (graph.isEmpty) {
      return [
        NativeRow('memory_graph_preview', l10n.noKnowledgeGraphYet,
            kind: 'navigation', subtitle: l10n.knowledgeGraphWillBuildAutomatically, action: _openGraph),
      ];
    }
    final projection = projectNativeGraph(graph, layout: 'card', height: 140, interactive: false, zoom: 0.6);
    if (projection == null) {
      return [NativeRow('memory_graph_open', l10n.mindMap, kind: 'navigation', action: _openGraph)];
    }
    return [NativeRow('memory_graph_preview', l10n.memoryGraph, kind: 'graph', graph: projection, action: _openGraph)];
  }

  Widget _buildShimmerMemoryList() {
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 120),
      child: ListView.builder(
        itemCount: 8, // Show 8 shimmer items
        itemBuilder: (context, index) {
          return ShimmerWithTimeout(
            baseColor: OmiColors.surface1,
            highlightColor: OmiColors.surface3,
            child: Container(
              margin: const EdgeInsets.only(bottom: AppStyles.spacingM),
              height: 88, // Approximate height of a memory item
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            ),
          );
        },
      ),
    );
  }

  void _showQuickEditSheet(BuildContext context, Memory memory, MemoriesProvider provider) {
    showMemoryQuickEditSheet(context, memory, provider);
  }

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0.0, duration: OmiMotion.emphasizedDuration, curve: OmiMotion.emphasizedCurve);
    }
  }

  void _showMemoryManagementSheet(BuildContext context, MemoriesProvider provider) {
    PlatformManager.instance.analytics.memoriesManagementSheetOpened();
    showOmiSheet<void>(
      context: context,
      title: context.l10n.memoryManagement,
      padding: EdgeInsets.zero,
      builder: (context) => MemoryManagementSheet(provider: provider),
      nativeBuilder: (context) => MemoryManagementSheet(provider: provider, native: true),
    );
  }
}

/// The mind map preview at the top of Memories: a compact skeleton while the graph loads, a
/// zoomed-out, non-interactive graph that opens the full graph on tap, or one Try Again row when
/// it fails. It loads on its own; the list below never waits on it.
class MemoryMindMapPreview extends StatelessWidget {
  const MemoryMindMapPreview({super.key, this.loadGraph = KnowledgeGraphApi.getKnowledgeGraph});

  final Future<Map<String, dynamic>> Function() loadGraph;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: MemoryGraphPage(
        embedded: true,
        preview: true,
        showAppBar: false,
        showShareButton: false,
        trackOpenEvent: false,
        initialZoom: 0.6,
        loadGraph: loadGraph,
        onOpen: () => routeToPage(context, MemoryGraphPage(trackOpenEvent: false, loadGraph: loadGraph)),
      ),
    );
  }
}
