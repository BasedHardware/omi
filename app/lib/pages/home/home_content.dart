import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/today_tasks_widget.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

class HomeContentPage extends StatefulWidget {
  const HomeContentPage({super.key});

  @override
  State<HomeContentPage> createState() => HomeContentPageState();
}

class HomeContentPageState extends State<HomeContentPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  List<DailySummary> _recentSummaries = [];
  bool _loadingSummaries = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSummaries());
  }

  Future<void> _loadSummaries() async {
    if (!mounted) return;
    setState(() => _loadingSummaries = true);
    final summaries = await getDailySummaries(limit: 3, offset: 0);
    if (mounted) {
      setState(() {
        _recentSummaries = summaries;
        _loadingSummaries = false;
      });
    }
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

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<ConversationProvider>(
      builder: (context, convoProvider, child) {
        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            await Future.wait([convoProvider.getInitialConversations(), _loadSummaries()]);
          },
          color: Colors.black,
          backgroundColor: Colors.white,
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // Live capture widget — shows when device or phone mic is recording
              const SliverToBoxAdapter(child: ConversationCaptureWidget()),

              // Today section — TodayTasksWidget has its own header
              const SliverToBoxAdapter(child: TodayTasksWidget()),

              // Daily Recaps section — hidden entirely when not loading and empty
              if (_loadingSummaries || _recentSummaries.isNotEmpty) ...[
                SliverToBoxAdapter(
                  child: _buildSectionHeader(
                    context,
                    context.l10n.dailyRecaps,
                    onViewAll: () {
                      if (!convoProvider.showDailySummaries) convoProvider.toggleDailySummaries();
                      context.read<HomeProvider>().setIndex(1);
                    },
                  ),
                ),
                SliverToBoxAdapter(child: _buildDailyRecapsPreview(context)),
              ],

              // Conversations section.
              //
              // If the user has fewer than 3 non-discarded conversations,
              // we replace the recent-conversations preview with three
              // big "get started" options so the home page doesn't feel
              // empty for new users.
              if (_nonDiscardedConversationCount(convoProvider) >= 3) ...[
                SliverToBoxAdapter(
                  child: _buildSectionHeader(
                    context,
                    context.l10n.conversations,
                    onViewAll: () {
                      // Reset the daily-summaries flag so the conversations tab
                      // actually shows conversations (it persists from Daily
                      // Recaps' View All otherwise).
                      if (convoProvider.showDailySummaries) convoProvider.toggleDailySummaries();
                      context.read<HomeProvider>().setIndex(1);
                    },
                  ),
                ),
                HomeConversationsPreview(conversationProvider: convoProvider),

                // Mind Map section — only shown for users with enough activity.
                SliverToBoxAdapter(
                  child: _buildSectionHeader(
                    context,
                    context.l10n.mindMap,
                    onViewAll: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (context) => const MemoryGraphPage(trackOpenEvent: false)),
                    ),
                    buttonLabel: context.l10n.expand,
                  ),
                ),
                SliverToBoxAdapter(child: _buildMindMapPreview(context)),

                // Bottom padding so content isn't hidden behind chat bar + nav
                const SliverToBoxAdapter(child: SizedBox(height: 160)),
              ] else if (convoProvider.isLoadingConversations || convoProvider.isFetchingConversations)
                // Hide both the recent-convos preview AND the get-started tiles
                // while we're still fetching — otherwise users with conversations
                // briefly see the new-user triangle UI while the network call
                // is in flight, which looks broken.
                const SliverFillRemaining(hasScrollBody: false, child: SizedBox.shrink())
              else
                // For new users (< 3 non-discarded convos): hide the conversations
                // preview AND the mind map. A quiet placeholder fills the space;
                // the + button beside the chat bar is the recording entry point.
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Padding(
                    // Bottom padding leaves room for the floating chat bar.
                    padding: const EdgeInsets.only(bottom: 160),
                    child: Center(
                      child: Text(
                        context.l10n.tapPlusToStartRecording,
                        style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  int _nonDiscardedConversationCount(ConversationProvider provider) {
    return provider.conversations.where((c) => !c.discarded).length;
  }

  Widget _buildSectionHeader(BuildContext context, String title, {VoidCallback? onViewAll, String? buttonLabel}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          GestureDetector(
            onTap: onViewAll,
            child: Text(
              title,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
            ),
          ),
          if (onViewAll != null)
            GestureDetector(
              onTap: onViewAll,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Text(
                  buttonLabel ?? context.l10n.viewAll,
                  style: TextStyle(color: Colors.grey[400], fontSize: 12, fontWeight: FontWeight.w500),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildDailyRecapsPreview(BuildContext context) {
    const cardHeight = DailySummaryCard.height;
    if (_loadingSummaries) {
      return Padding(
        padding: const EdgeInsets.only(top: 12),
        child: SizedBox(
          height: cardHeight,
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(left: 16),
            itemCount: 3,
            itemBuilder: (_, __) => Padding(
              padding: const EdgeInsets.only(right: 12),
              child: ShimmerWithTimeout(
                baseColor: AppStyles.backgroundSecondary,
                highlightColor: AppStyles.backgroundTertiary,
                child: Container(
                  width: DailySummaryCard.width,
                  decoration: BoxDecoration(
                    color: AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    if (_recentSummaries.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 12),
      child: SizedBox(
        height: cardHeight,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.only(left: 16),
          itemCount: _recentSummaries.length,
          itemBuilder: (context, index) => _buildSummaryCard(context, _recentSummaries[index]),
        ),
      ),
    );
  }

  Widget _buildSummaryCard(BuildContext context, DailySummary summary) {
    return DailySummaryCard(
      summary: summary,
      dateLabel: _formatDate(context, summary.date),
      onTap: () async {
        PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: summary.id, date: summary.date);
        // Detail page pops with ``{deleted: true, summaryId}`` when the user
        // deletes from there — drop the card so the home recap row doesn't
        // linger until the next pull-to-refresh.
        final result = await Navigator.push<dynamic>(
          context,
          MaterialPageRoute(
            builder: (context) => DailySummaryDetailPage(summaryId: summary.id, summary: summary),
          ),
        );
        if (!mounted) return;
        if (result is Map && result['deleted'] == true) {
          final deletedId = result['summaryId'] as String?;
          if (deletedId != null) {
            setState(() => _recentSummaries.removeWhere((s) => s.id == deletedId));
          }
        }
      },
    );
  }

  String _formatDate(BuildContext context, String dateStr) {
    final parts = dateStr.split('-');
    if (parts.length != 3) return dateStr;
    final year = int.tryParse(parts[0]) ?? 2024;
    final month = int.tryParse(parts[1]) ?? 1;
    final day = int.tryParse(parts[2]) ?? 1;
    final date = DateTime(year, month, day);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    if (date == today) return context.l10n.today;
    if (date == yesterday) return context.l10n.yesterday;
    const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${weekdays[date.weekday - 1]}, ${months[month - 1]} $day';
  }

  Widget _buildMindMapPreview(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (context) => const MemoryGraphPage(trackOpenEvent: false)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: const SizedBox(
            height: 180,
            child: IgnorePointer(
              child: MemoryGraphPage(
                embedded: true,
                showAppBar: false,
                showShareButton: false,
                trackOpenEvent: false,
                initialZoom: 0.6,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The filtered recent-conversation preview shown on Home for established users.
///
/// This consumes [ConversationProvider.groupedConversations], which already
/// carries the conversations page's discarded/short/starred/date filters.
class HomeConversationsPreview extends StatelessWidget {
  final ConversationProvider conversationProvider;

  const HomeConversationsPreview({super.key, required this.conversationProvider});

  @override
  Widget build(BuildContext context) {
    if (conversationProvider.isLoadingConversations && conversationProvider.conversations.isEmpty) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            children: List.generate(
              2,
              (_) => Padding(
                padding: const EdgeInsets.only(top: 12),
                child: ShimmerWithTimeout(
                  baseColor: AppStyles.backgroundSecondary,
                  highlightColor: AppStyles.backgroundTertiary,
                  child: Container(
                    height: 80,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundSecondary,
                      borderRadius: BorderRadius.circular(24),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    final sortedDates = conversationProvider.groupedConversations.keys.toList()..sort((a, b) => b.compareTo(a));
    final recent = <ServerConversation>[];
    for (final date in sortedDates) {
      final list = conversationProvider.groupedConversations[date] ?? const [];
      for (final conversation in list) {
        recent.add(conversation);
        if (recent.length >= 3) break;
      }
      if (recent.length >= 3) break;
    }
    if (recent.isEmpty) return const SliverToBoxAdapter(child: SizedBox.shrink());

    return SliverList(
      delegate: SliverChildBuilderDelegate(childCount: recent.length, (context, index) {
        final conversation = recent[index];
        final date = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);
        return ConversationListItem(
          key: ValueKey(conversation.id),
          conversation: conversation,
          date: date,
          conversationIdx: index,
        );
      }),
    );
  }
}
