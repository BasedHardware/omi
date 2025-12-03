import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/search_result_header_widget.dart';
import 'package:omi/pages/conversations/widgets/search_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_conversations.dart';
import 'widgets/conversations_group_widget.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
      if (conversationProvider.conversations.isEmpty) {
        await conversationProvider.getInitialConversations();
      }

      // Check if we should show the app review prompt for first conversation
      if (mounted && conversationProvider.conversations.isNotEmpty) {
        await _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: true);
      }
    });
    super.initState();
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

  Widget _buildMergeToolbar(ConversationProvider provider) {
    int selectedCount = provider.selectedConversationIds.length;
    bool canMerge = provider.canMergeSelected();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        border: Border(
          top: BorderSide(
            color: Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            // Cancel button
            TextButton.icon(
              onPressed: () {
                HapticFeedback.lightImpact();
                provider.exitMergeMode();
              },
              icon: const Icon(Icons.close, color: Colors.white70),
              label: const Text(
                'Cancel',
                style: TextStyle(color: Colors.white70, fontSize: 16),
              ),
            ),
            const SizedBox(width: 16),
            // Selection count
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Text(
                  '$selectedCount selected',
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ),
            // Merge button
            ElevatedButton.icon(
              onPressed: canMerge && !provider.isMergingConversations
                  ? () async {
                      HapticFeedback.mediumImpact();
                      await _showMergePreviewDialog(provider);
                    }
                  : null,
              icon: provider.isMergingConversations
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    )
                  : const Icon(Icons.merge_type, size: 20),
              label: Text(provider.isMergingConversations ? 'Merging...' : 'Merge'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.deepPurpleAccent,
                foregroundColor: Colors.white,
                disabledBackgroundColor: Colors.grey.shade800,
                disabledForegroundColor: Colors.grey.shade600,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showMergePreviewDialog(ConversationProvider provider) async {
    final selectedConvos =
        provider.conversations.where((c) => provider.selectedConversationIds.contains(c.id)).toList();

    // Sort by creation date
    selectedConvos.sort((a, b) => a.createdAt.compareTo(b.createdAt));

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text(
          'Merge Conversations',
          style: TextStyle(color: Colors.white),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'You are about to merge ${selectedConvos.length} conversations:',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 16),
              ...selectedConvos.map((convo) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        Text(
                          convo.structured.emoji,
                          style: const TextStyle(fontSize: 20),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            convo.structured.title,
                            style: const TextStyle(color: Colors.white),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  )),
              const SizedBox(height: 16),
              const Text(
                'This will combine all transcripts in chronological order. You can undo this action for 24 hours.',
                style: TextStyle(color: Colors.white54, fontSize: 13),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.deepPurpleAccent,
              foregroundColor: Colors.white,
            ),
            child: const Text('Merge'),
          ),
        ],
      ),
    );

    if (result == true && mounted) {
      final mergeResult = await provider.executeMerge();

      if (mergeResult != null && mounted) {
        // Show undo snackbar
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Conversations merged successfully'),
            duration: const Duration(seconds: 8),
            action: SnackBarAction(
              label: 'Undo',
              textColor: Colors.deepPurpleAccent,
              onPressed: () async {
                await provider.undoMerge(mergeResult.mergedConversationId);
              },
            ),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('building conversations page');
    super.build(context);
    return Consumer<ConversationProvider>(builder: (context, convoProvider, child) {
      return Stack(
        children: [
          RefreshIndicator(
            onRefresh: () async {
              HapticFeedback.mediumImpact();
              Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
              await convoProvider.getInitialConversations();
              return;
            },
            color: Colors.deepPurpleAccent,
            backgroundColor: Colors.white,
            child: CustomScrollView(
              controller: _scrollController,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                // const SliverToBoxAdapter(child: SizedBox(height: 16)), // above capture widget
                const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
                const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
                const SliverToBoxAdapter(child: ConversationCaptureWidget()),
                const SliverToBoxAdapter(child: SizedBox(height: 12)), // above search widget
                const SliverToBoxAdapter(child: SearchWidget()),
                const SliverToBoxAdapter(child: SizedBox(height: 0)), //below search widget
                const SliverToBoxAdapter(child: SearchResultHeaderWidget()),
                getProcessingConversationsWidget(convoProvider.processingConversations),
                if (convoProvider.groupedConversations.isEmpty && !convoProvider.isLoadingConversations)
                  const SliverToBoxAdapter(
                    child: Center(
                      child: Padding(
                        padding: EdgeInsets.only(top: 32.0),
                        child: EmptyConversationsWidget(),
                      ),
                    ),
                  )
                else if (convoProvider.groupedConversations.isEmpty && convoProvider.isLoadingConversations)
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
                const SliverToBoxAdapter(
                  child: SizedBox(height: 80),
                ),
              ],
            ),
          ),
          // Merge mode toolbar
          if (convoProvider.isMergeMode)
            Positioned(
              left: 0,
              right: 0,
              bottom: 95,
              child: _buildMergeToolbar(convoProvider),
            ),
        ],
      );
    });
  }
}
