import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/home/widgets/home_first_day.dart';
import 'package:omi/pages/home/widgets/home_sections.dart';
import 'package:omi/pages/home/widgets/idle_capture_card.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';

class HomeContentPage extends StatefulWidget {
  const HomeContentPage({super.key, this.fetchSummaries});

  /// Defaults to the daily-summaries API (the latest recap card).
  final DailySummariesFetcher? fetchSummaries;

  @override
  State<HomeContentPage> createState() => HomeContentPageState();
}

class HomeContentPageState extends State<HomeContentPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  List<DailySummary> _recentSummaries = [];

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSummaries());
  }

  Future<void> _loadSummaries() async {
    if (!mounted) return;
    final result = await (widget.fetchSummaries ?? getDailySummaries)(limit: 3, offset: 0);
    // Keep the card that is already there when the read fails (cached content refreshes in place).
    if (mounted && result.ok) setState(() => _recentSummaries = result.items);
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
        final count = _nonDiscardedConversationCount(convoProvider);
        // While the first page is still loading an established account looks empty; wait before
        // showing first-day content so it never flashes.
        final settled = count > 0 || !(convoProvider.isLoadingConversations || convoProvider.isFetchingConversations);
        final firstDay = settled && count == 0;
        return RefreshIndicator(
          onRefresh: () async {
            OmiHaptics.medium();
            await Future.wait([convoProvider.getInitialConversations(), _loadSummaries()]);
          },
          color: OmiColors.onAccent,
          backgroundColor: OmiColors.accent,
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // v2 Main, top to bottom: greeting, what is live, pendant sync, the latest recap, recent
              // conversations, what is up next, the week, and what Omi learned. 22pt between sections.
              // The first day (v2 FirstDay) welcomes instead, shows "Omi is listening" while it
              // is, and adds Getting started and Good to know, so Home is never empty.
              SliverToBoxAdapter(child: firstDay ? const HomeFirstDayHeader() : _buildGreeting(context)),

              // Live capture widget — shows when device or phone mic is recording; its quiet twin
              // (how to start listening) takes the same place when nothing is.
              if (firstDay)
                const SliverToBoxAdapter(child: FirstDayListeningHero())
              else
                const SliverToBoxAdapter(child: ConversationCaptureWidget(showsCall: true)),
              const SliverToBoxAdapter(child: IdleCaptureCard()),

              const SliverToBoxAdapter(child: CaptureRecoveryBanner()),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSize.screenMargin),
                sliver: SliverList.list(
                  children: [
                    HomeSyncCard(onTap: () => _openSync(context)),
                    if (_recentSummaries.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 22),
                        child: HomeRecapCard(
                          summary: _recentSummaries.first,
                          onTap: () => _openRecap(context, _recentSummaries.first),
                        ),
                      ),
                    // Until the first few conversations: the setup checklist (folds away when done).
                    if (settled && count < 3) HomeGettingStarted(conversationCount: count),
                  ],
                ),
              ),

              // The latest conversations, short: up to three, from the very first one.
              if (count > 0) ...[
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(OmiSize.screenMargin, 22, OmiSize.screenMargin, 0),
                  sliver: SliverToBoxAdapter(
                    child: HomeSectionHeader(
                      title: context.l10n.conversations,
                      actionLabel: context.l10n.seeAll,
                      onAction: () => context.read<HomeProvider>().setIndex(1),
                    ),
                  ),
                ),
                HomeConversationsPreview(conversationProvider: convoProvider),
              ],

              if (settled) ...[
                // To do, short, then the week and what Omi learned (each hides when it has nothing).
                SliverPadding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSize.screenMargin),
                  sliver: SliverList.list(
                    children: [
                      HomeUpNext(onAllTasks: () => context.read<HomeProvider>().setIndex(2)),
                      const HomeThisWeek(),
                      HomeNewMemories(onTap: () => routeToPage(context, const MemoriesPage())),
                    ],
                  ),
                ),
                if (firstDay) const SliverToBoxAdapter(child: HomeGoodToKnow()),
              ],

              // Bottom padding so content isn't hidden behind chat bar + nav
              SliverToBoxAdapter(child: SizedBox(height: homeChatBarClearance(context))),
            ],
          ),
        );
      },
    );
  }

  void _openSync(BuildContext context) {
    OmiHaptics.selection();
    final page = context.read<DeviceProvider>().supportsMultiFileSync ? const AutoSyncPage() : const SyncPage();
    routeToPage(context, page);
  }

  Future<void> _openRecap(BuildContext context, DailySummary summary) async {
    PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: summary.id, date: summary.date);
    // Detail page pops with ``{deleted: true, summaryId}`` when the user
    // deletes from there — drop the card so it doesn't linger until the next pull-to-refresh.
    final result = await routeToPage(
      context,
      DailySummaryDetailPage(summaryId: summary.id, summary: summary, days: List.of(_recentSummaries)),
    );
    if (!mounted) return;
    if (result is Map && result['deleted'] == true) {
      final deletedId = result['summaryId'] as String?;
      if (deletedId != null) {
        setState(() => _recentSummaries.removeWhere((s) => s.id == deletedId));
      }
    }
  }

  int _nonDiscardedConversationCount(ConversationProvider provider) {
    return provider.conversations.where((c) => !c.discarded).length;
  }

  /// v2 Main: "Good afternoon" as the large title, then the user's first name and today's date.
  Widget _buildGreeting(BuildContext context) {
    final l10n = context.l10n;
    final now = DateTime.now();
    final greeting = now.hour < 12
        ? l10n.goodMorning
        : now.hour < 18
            ? l10n.goodAfternoon
            : l10n.goodEvening;
    final name = SharedPreferencesUtil().givenName.trim();
    final day = OmiDateFormat.of(context).longDay(now);
    return Padding(
      // v2: the title sits 4pt inside the 16pt page margin, like every large title.
      padding:
          const EdgeInsets.fromLTRB(OmiSize.screenMargin + OmiSpacing.xxs, OmiSpacing.xxs, OmiSize.screenMargin, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(greeting, style: OmiType.largeTitle, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(height: 2),
          Text(
            name.isEmpty ? day : '$name · $day',
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
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
                    decoration: BoxDecoration(color: AppStyles.backgroundSecondary, borderRadius: OmiRadius.xlAll),
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
        // v2: Home's recent conversations share one card.
        final first = index == 0;
        final last = index == recent.length - 1;
        return ConversationListItem(
          key: ValueKey(conversation.id),
          conversation: conversation,
          date: date,
          conversationIdx: index,
          allowSelection: false,
          position: first && last
              ? ConversationRowPosition.only
              : first
                  ? ConversationRowPosition.first
                  : last
                      ? ConversationRowPosition.last
                      : ConversationRowPosition.middle,
        );
      }),
    );
  }
}
