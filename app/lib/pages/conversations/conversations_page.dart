import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/phone_calls/active_call_banner.dart';
import 'package:omi/pages/conversations/widgets/search_result_header_widget.dart';
import 'package:omi/pages/conversations/widgets/search_widget.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'widgets/conversations_group_widget.dart';
import 'widgets/empty_conversations.dart';

class ConversationsPage extends StatefulWidget {
  const ConversationsPage({super.key});

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  final AppReviewService _appReviewService = AppReviewService();
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<GoalsWidgetState> _goalsWidgetKey = GlobalKey<GoalsWidgetState>();

  void _refreshGoals() {}

  // Public method to trigger goal creation from outside
  void addGoal() {
    _goalsWidgetKey.currentState?.addGoal();
  }

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final conversationProvider = context.read<ConversationProvider>();
      if (conversationProvider.conversations.isEmpty) {
        await conversationProvider.getInitialConversations();
      } else {
        // Still check for daily summaries even if conversations are cached
        conversationProvider.checkHasDailySummaries();
      }

      if (!mounted) return;

      // Load folders for folder tabs
      final folderProvider = context.read<FolderProvider>();
      if (folderProvider.folders.isEmpty) {
        await folderProvider.loadFolders();
      }

      // Check if we should show the app review prompt for first conversation
      if (mounted && conversationProvider.conversations.isNotEmpty) {
        await _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: true);
      }
    });
  }

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0.0, duration: const Duration(milliseconds: 500), curve: Curves.easeOutCubic);
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Widget _buildConversationShimmer() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Date header shimmer
          ShimmerWithTimeout(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              width: 100,
              height: 16,
              decoration: BoxDecoration(color: AppStyles.backgroundSecondary, borderRadius: BorderRadius.circular(8)),
            ),
          ),
          const SizedBox(height: 12),
          // Conversation items shimmer
          ...List.generate(
            3,
            (index) => Padding(
              padding: const EdgeInsets.only(bottom: 16.0),
              child: ShimmerWithTimeout(
                baseColor: AppStyles.backgroundSecondary,
                highlightColor: AppStyles.backgroundTertiary,
                child: Container(
                  height: 80,
                  decoration: BoxDecoration(
                    color: AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  int _nonDiscardedConversationCount(ConversationProvider provider) {
    return provider.conversations.where((c) => !c.discarded).length;
  }

  Widget _buildNoConversationsHero(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 0, 32, 120),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Layered icon: soft purple aura behind a tactile glassy tile.
          Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 160,
                height: 160,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      Colors.deepPurple.withValues(alpha: 0.35),
                      Colors.deepPurple.withValues(alpha: 0.0),
                    ],
                    stops: const [0.0, 1.0],
                  ),
                ),
              ),
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(26),
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFF7B5CFF), Color(0xFF5733E0)],
                  ),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.08), width: 1),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.deepPurple.withValues(alpha: 0.45),
                      blurRadius: 30,
                      spreadRadius: 2,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: const Icon(Icons.forum_rounded, size: 42, color: Colors.white),
              ),
            ],
          ),
          const SizedBox(height: 28),
          const Text(
            'No conversations yet',
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 280),
            child: Text(
              'Conversations you record show up here. Tap a tile on the home tab to start your first one.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 15,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingShimmer() {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) => _buildConversationShimmer(),
        childCount: 3, // Show 3 shimmer conversation groups
      ),
    );
  }

  Widget _buildLoadMoreShimmer() {
    return Padding(
      padding: const EdgeInsets.only(top: 16.0),
      child: ShimmerWithTimeout(
        baseColor: AppStyles.backgroundSecondary,
        highlightColor: AppStyles.backgroundTertiary,
        child: Container(
          height: 60,
          margin: const EdgeInsets.symmetric(horizontal: 16.0),
          decoration: BoxDecoration(color: AppStyles.backgroundSecondary, borderRadius: BorderRadius.circular(12)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    Logger.debug('building conversations page');
    super.build(context);
    return Consumer<ConversationProvider>(
      builder: (context, convoProvider, child) {
        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
            // Refresh goals widget
            _goalsWidgetKey.currentState?.refresh();
            _refreshGoals();
            await Future.wait([
              convoProvider.getInitialConversations(),
              Provider.of<FolderProvider>(context, listen: false).loadFolders(),
            ]);
          },
          color: Colors.deepPurpleAccent,
          backgroundColor: Colors.white,
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // Header widgets (unchanged)
              const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
              const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
              const SliverToBoxAdapter(child: ActiveCallBanner()),

              // Search bar
              Consumer2<HomeProvider, ConversationProvider>(
                builder: (context, homeProvider, convoProvider, _) {
                  bool shouldShowSearchBar = homeProvider.showConvoSearchBar || convoProvider.previousQuery.isNotEmpty;
                  if (!shouldShowSearchBar) {
                    return const SliverToBoxAdapter(child: SizedBox.shrink());
                  }
                  return const SliverToBoxAdapter(
                    child: Column(children: [SizedBox(height: 12), SearchWidget(), SizedBox(height: 12)]),
                  );
                },
              ),
              const SliverToBoxAdapter(child: SearchResultHeaderWidget()),
              getProcessingConversationsWidget(convoProvider.processingConversations),

              // Today's Tasks and Goals widgets - hide when showing daily recaps, search bar is active, or calendar filter is active
              Consumer<HomeProvider>(
                builder: (context, homeProvider, _) {
                  final isSearchActive = homeProvider.showConvoSearchBar || convoProvider.previousQuery.isNotEmpty;
                  final hasCalendarFilter = convoProvider.selectedDate != null;
                  final prefs = SharedPreferencesUtil();
                  if (convoProvider.showDailySummaries || isSearchActive || hasCalendarFilter) {
                    return const SliverToBoxAdapter(child: SizedBox.shrink());
                  }
                  final showGoals = prefs.showGoalTrackerEnabled;
                  if (!showGoals) {
                    return const SliverToBoxAdapter(child: SizedBox.shrink());
                  }
                  return SliverToBoxAdapter(
                    child: Column(
                      children: [
                        if (showGoals) GoalsWidget(key: _goalsWidgetKey, onRefresh: _refreshGoals),
                      ],
                    ),
                  );
                },
              ),

              // Section header - show "Daily Recaps" or "Conversations" with optional recording pill.
              // Hidden entirely when the user has fewer than 3 non-discarded
              // conversations (and isn't on the Daily Recaps view) — those
              // users get the empty-state hero below instead.
              if (convoProvider.showDailySummaries ||
                  _nonDiscardedConversationCount(convoProvider) >= 3 ||
                  convoProvider.isLoadingConversations ||
                  convoProvider.isFetchingConversations)
                SliverToBoxAdapter(
                  child: Builder(
                    builder: (context) => Padding(
                      padding: const EdgeInsets.only(left: 24, right: 16, top: 16, bottom: 8),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Text(
                            convoProvider.showDailySummaries ? context.l10n.dailyRecaps : context.l10n.conversations,
                            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

              // Folder tabs - hide when showing daily recaps OR when the user
              // hasn't built up enough conversations yet (matches the title).
              if (!convoProvider.showDailySummaries &&
                  (_nonDiscardedConversationCount(convoProvider) >= 3 ||
                      convoProvider.isLoadingConversations ||
                      convoProvider.isFetchingConversations))
                Consumer2<FolderProvider, ConversationProvider>(
                  builder: (context, folderProvider, convoProvider, _) {
                    return SliverToBoxAdapter(
                      child: FolderTabs(
                        folders: folderProvider.folders,
                        selectedFolderId: convoProvider.selectedFolderId,
                        onFolderSelected: (folderId) {
                          convoProvider.filterByFolder(folderId);
                        },
                        showStarredOnly: convoProvider.showStarredOnly,
                        onStarredToggle: convoProvider.toggleStarredFilter,
                        showDailySummaries: convoProvider.showDailySummaries,
                        onDailySummariesToggle: convoProvider.toggleDailySummaries,
                        hasDailySummaries: convoProvider.hasDailySummaries,
                      ),
                    );
                  },
                ),
              // Show daily summaries list or conversations based on filter
              if (convoProvider.showDailySummaries)
                const DailySummariesList()
              else if (_nonDiscardedConversationCount(convoProvider) < 3 &&
                  !convoProvider.isLoadingConversations &&
                  !convoProvider.isFetchingConversations &&
                  !convoProvider.showStarredOnly &&
                  convoProvider.selectedFolderId == null)
                // Friendly hero for users who haven't built up enough
                // conversations yet — matches the polished Tasks empty state.
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: _buildNoConversationsHero(context)),
                )
              else if (convoProvider.groupedConversations.isEmpty &&
                  !convoProvider.isLoadingConversations &&
                  !convoProvider.isFetchingConversations)
                SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 32.0),
                      child: EmptyConversationsWidget(isStarredFilterActive: convoProvider.showStarredOnly),
                    ),
                  ),
                )
              else if (convoProvider.groupedConversations.isEmpty &&
                  (convoProvider.isLoadingConversations || convoProvider.isFetchingConversations))
                _buildLoadingShimmer()
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(childCount: convoProvider.groupedConversations.length + 1, (
                    context,
                    index,
                  ) {
                    if (index == convoProvider.groupedConversations.length) {
                      Logger.debug('loading more conversations');
                      if (convoProvider.isLoadingConversations) {
                        return _buildLoadMoreShimmer();
                      }
                      // widget.loadMoreMemories(); // CALL this only when visible
                      return VisibilityDetector(
                        key: const Key('conversations-key'),
                        onVisibilityChanged: (visibilityInfo) {
                          var provider = Provider.of<ConversationProvider>(context, listen: false);
                          if (provider.previousQuery.isNotEmpty) {
                            if (visibilityInfo.visibleFraction > 0 &&
                                !provider.isLoadingConversations &&
                                (provider.totalSearchPages > provider.currentSearchPage)) {
                              provider.searchMoreConversations();
                            }
                          } else {
                            if (visibilityInfo.visibleFraction > 0 && !convoProvider.isLoadingConversations) {
                              convoProvider.getMoreConversationsFromServer();
                            }
                          }
                        },
                        child: const SizedBox(height: 20, width: double.maxFinite),
                      );
                    } else {
                      var date = convoProvider.groupedConversations.keys.elementAt(index);
                      List<ServerConversation> memoriesForDate = convoProvider.groupedConversations[date]!;
                      return Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (index == 0) const SizedBox(height: 10),
                          ConversationsGroupWidget(
                            key: ValueKey(date),
                            isFirst: index == 0,
                            conversations: memoriesForDate,
                            date: date,
                          ),
                        ],
                      );
                    }
                  }),
                ),
              SliverToBoxAdapter(child: SizedBox(height: convoProvider.isSelectionModeActive ? 160 : 100)),
            ],
          ),
        );
      },
    );
  }
}
