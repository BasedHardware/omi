import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'widgets/memory_dialog.dart';
import 'widgets/memory_edit_sheet.dart';
import 'widgets/memory_graph_page.dart';
import 'widgets/memory_history_status_banner.dart';
import 'widgets/memory_item.dart';
import 'widgets/memory_management_sheet.dart';
import 'widgets/memories_load_error.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => MemoriesPageState();
}

class MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  bool _isInitialLoad = true;
  String? _highlightedMemoryId;
  Timer? _highlightTimer;

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
    _highlightTimer?.cancel();
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
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
            icon: const FaIcon(FontAwesomeIcons.brain, size: 16),
            label: context.l10n.memoryGraph,
            diameter: 40,
            onPressed: loading ? null : () => routeToPage(context, const MemoryGraphPage()),
          ),
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
        return Scaffold(
          backgroundColor: OmiColors.surface0,
          appBar: AppBar(
            leading: const OmiBackButton(),
            title: Text(context.l10n.memories),
          ),
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
                          SliverToBoxAdapter(child: _buildHeader(provider, loading: false)),
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
      },
    );
  }

  Widget _buildShimmerMemoryList() {
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 120),
      child: ListView.builder(
        itemCount: 8, // Show 8 shimmer items
        itemBuilder: (context, index) {
          return ShimmerWithTimeout(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              margin: const EdgeInsets.only(bottom: AppStyles.spacingM),
              height: 88, // Approximate height of a memory item
              decoration: const BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: OmiRadius.mdAll,
              ),
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
    );
  }
}
