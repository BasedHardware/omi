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
import 'widgets/conversation_list_item.dart';

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

  List<Widget> _buildConversationsWithStickyHeaders(ConversationProvider convoProvider) {
    List<Widget> slivers = [];
    int groupIndex = 0;

    for (var entry in convoProvider.groupedConversations.entries) {
      var date = entry.key;
      List<ServerConversation> conversations = entry.value;
      final isFirst = groupIndex == 0;

      // Add sticky header for date
      slivers.add(
        SliverPersistentHeader(
          pinned: true,
          delegate: _StickyDateHeaderDelegate(
            date: date,
            isFirst: isFirst,
          ),
        ),
      );

      // Add conversations for this date
      slivers.add(
        SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              return ConversationListItem(
                conversation: conversations[index],
                conversationIdx: index,
                date: date,
              );
            },
            childCount: conversations.length,
          ),
        ),
      );

      slivers.add(const SliverToBoxAdapter(child: SizedBox(height: 10)));
      groupIndex++;
    }

    // Add load more indicator
    slivers.add(
      SliverToBoxAdapter(
        child: convoProvider.isLoadingConversations
            ? _buildLoadMoreShimmer()
            : VisibilityDetector(
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
              ),
      ),
    );

    return slivers;
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
          await convoProvider.getInitialConversations();
          return;
        },
        color: const Color(0xFF3B82F6),
        backgroundColor: Colors.black,
        child: CustomScrollView(
          controller: _scrollController,
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // const SliverToBoxAdapter(child: SizedBox(height: 16)), // above capture widget
            const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
            const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
            const SliverToBoxAdapter(child: ConversationCaptureWidget()),
            const SliverToBoxAdapter(child: SizedBox(height: 0)), // above search widget
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
              ..._buildConversationsWithStickyHeaders(convoProvider),
            const SliverToBoxAdapter(
              child: SizedBox(height: 80),
            ),
          ],
        ),
      );
    });
  }
}

// Sticky Date Header Delegate
class _StickyDateHeaderDelegate extends SliverPersistentHeaderDelegate {
  final DateTime date;
  final bool isFirst;

  _StickyDateHeaderDelegate({
    required this.date,
    required this.isFirst,
  });

  @override
  double get minExtent => isFirst ? 20.0 : 32.0;

  @override
  double get maxExtent => isFirst ? 20.0 : 32.0;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    var now = DateTime.now();
    var yesterday = now.subtract(const Duration(days: 1));
    var isToday = date.month == now.month && date.day == now.day && date.year == now.year;
    var isYesterday = date.month == yesterday.month && date.day == yesterday.day && date.year == yesterday.year;

    // Calculate opacity based on shrink offset to create push effect
    // When a header is being pushed out, it will fade and be pushed up
    final opacity = (1.0 - (shrinkOffset / maxExtent)).clamp(0.0, 1.0);
    final topPadding = isFirst ? 0.0 : 12.0 - (shrinkOffset * 0.5).clamp(0.0, 12.0);

    return SizedBox(
      height: maxExtent,
      child: Transform.translate(
        offset: Offset(0, -shrinkOffset),
        child: Opacity(
          opacity: opacity,
          child: Container(
            color: const Color(0xFF0F0F12), // Background color matching app theme
            padding: EdgeInsets.fromLTRB(16, topPadding, 16, 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.start,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Text(
                  isToday
                      ? 'Today'
                      : isYesterday
                          ? 'Yesterday'
                          : _formatDate(date),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Container(
                    height: 1,
                    color: const Color(0xFF35343B),
                  ),
                )
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${months[date.month - 1]} ${date.day}';
  }

  @override
  bool shouldRebuild(_StickyDateHeaderDelegate oldDelegate) {
    return date != oldDelegate.date || isFirst != oldDelegate.isFirst;
  }
}
