import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/search_result_header_widget.dart';
import 'package:omi/pages/conversations/widgets/search_widget.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/pages/conversations/widgets/wrapped_banner.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_conversations.dart';
import 'widgets/conversations_group_widget.dart';
import 'widgets/goal_tracker_widget.dart';

class ConversationsPage extends StatefulWidget {
  const ConversationsPage({super.key});

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  final AppReviewService _appReviewService = AppReviewService();
  final ScrollController _scrollController = ScrollController();

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
      _scrollController.animateTo(
        0.0,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOutCubic,
      );
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
          Shimmer.fromColors(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              width: 100,
              height: 16,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
          const SizedBox(height: 12),
          // Conversation items shimmer
          ...List.generate(
              3,
              (index) => Padding(
                    padding: const EdgeInsets.only(bottom: 16.0),
                    child: Shimmer.fromColors(
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
                  )),
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
      child: Shimmer.fromColors(
        baseColor: AppStyles.backgroundSecondary,
        highlightColor: AppStyles.backgroundTertiary,
        child: Container(
          height: 60,
          margin: const EdgeInsets.symmetric(horizontal: 16.0),
          decoration: BoxDecoration(
            color: AppStyles.backgroundSecondary,
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('building conversations page');
    super.build(context);
    return Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
      return RefreshIndicator(
        onRefresh: () async {
          HapticFeedback.mediumImpact();
          Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
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
            // Wrapped 2025 Banner
            const SliverToBoxAdapter(child: WrappedBanner()),
            // const SliverToBoxAdapter(child: SizedBox(height: 16)), // above capture widget
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            const SliverToBoxAdapter(child: ConversationCaptureWidget()),
            Consumer2<HomeProvider, ConversationProvider>(
              builder: (context, homeProvider, convoProvider, _) {
                // Show search bar if explicitly shown OR if there's an active search query
                bool shouldShowSearchBar = homeProvider.showConvoSearchBar || convoProvider.previousQuery.isNotEmpty;
                if (!shouldShowSearchBar) {
                  return const SliverToBoxAdapter(child: SizedBox.shrink());
                }
                return const SliverToBoxAdapter(
                  child: Column(
                    children: [
                      SizedBox(height: 12), // above search widget
                      SearchWidget(),
                      SizedBox(height: 12), //below search widget
                    ],
                  ),
                );
              },
            ),
            const SliverToBoxAdapter(child: SearchResultHeaderWidget()),
            getProcessingConversationsWidget(convoProvider.processingConversations),
            // Goal tracker widget - before folders
            Selector<DeveloperModeProvider, bool>(
              selector: (context, provider) => provider.showGoalTrackerEnabled,
              builder: (context, showGoalTrackerEnabled, child) {
                if (!showGoalTrackerEnabled) return const SliverToBoxAdapter(child: SizedBox.shrink());
                return const SliverToBoxAdapter(child: GoalTrackerWidget());
              },
            ),
            // Folder tabs
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
            else if (convoProvider.groupedConversations.isEmpty &&
                !convoProvider.isLoadingConversations &&
                !convoProvider.isFetchingConversations)
              SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 32.0),
                    child: EmptyConversationsWidget(
                      isStarredFilterActive: convoProvider.showStarredOnly,
                    ),
                  ),
                ),
              )
            else if (convoProvider.groupedConversations.isEmpty &&
                (convoProvider.isLoadingConversations || convoProvider.isFetchingConversations))
              _buildLoadingShimmer()
            else
              SliverList(
                delegate: SliverChildBuilderDelegate(
                  childCount: convoProvider.groupedConversations.length + 1,
                  (context, index) {
                    if (index == convoProvider.groupedConversations.length) {
                      debugPrint('loading more conversations');
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
                            isFirst: index == 0,
                            conversations: memoriesForDate,
                            date: date,
                          ),
                        ],
                      );
                    }
                  },
                ),
              ),
            SliverToBoxAdapter(
              child: SizedBox(height: convoProvider.isSelectionModeActive ? 160 : 100),
            ),
          ],
        ),
      );
    });
  }
}
