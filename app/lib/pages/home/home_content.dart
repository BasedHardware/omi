import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/today_tasks_widget.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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
          color: Colors.deepPurpleAccent,
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
                _buildConversationsPreview(convoProvider),

                // Mind Map section — only shown for users with enough activity.
                SliverToBoxAdapter(
                  child: _buildSectionHeader(
                    context,
                    context.l10n.mindMap,
                    onViewAll: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (context) => const MemoryGraphPage(trackOpenEvent: false)),
                    ),
                  ),
                ),
                SliverToBoxAdapter(child: _buildMindMapPreview(context)),

                // Bottom padding so content isn't hidden behind chat bar + nav
                const SliverToBoxAdapter(child: SizedBox(height: 160)),
              ] else
                // For new users (< 3 non-discarded convos): hide the conversations
                // preview AND the mind map. The 3 "get started" tiles fill the
                // remaining vertical space and sit centered between Today/Daily
                // Recaps above and the floating chat bar below.
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Padding(
                    // Bottom padding leaves room for the floating chat bar.
                    padding: const EdgeInsets.only(bottom: 160),
                    child: Center(child: _buildGetStartedOptions(context)),
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

  Widget _buildGetStartedOptions(BuildContext context) {
    Widget option({
      required IconData icon,
      required String label,
      required VoidCallback onTap,
    }) {
      return GestureDetector(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 88,
              height: 88,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF7B5CFF), Color(0xFF5733E0)],
                ),
                border: Border.all(color: Colors.white.withValues(alpha: 0.08), width: 1),
                boxShadow: [
                  BoxShadow(
                    color: Colors.deepPurple.withValues(alpha: 0.45),
                    blurRadius: 28,
                    spreadRadius: 1,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Icon(icon, color: Colors.white, size: 32),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: 96,
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  height: 1.2,
                ),
              ),
            ),
          ],
        ),
      );
    }

    final phoneOption = option(
      icon: Icons.mic_rounded,
      label: 'Record with Phone',
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const ConversationCapturingPage()),
        );
      },
    );
    final callOption = option(
      icon: Icons.phone_in_talk_rounded,
      label: 'Record Call',
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const PhoneCallsPage()),
        );
      },
    );
    final deviceOption = option(
      icon: Icons.bluetooth_searching_rounded,
      label: 'Connect Device',
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const DeviceSelectionPage()),
        );
      },
    );

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 28, 16, 24),
      child: Column(
        children: [
          // Top of the triangle: Record with Phone (the simplest path).
          phoneOption,
          const SizedBox(height: 22),
          // Bottom of the triangle: the other two side by side.
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              callOption,
              deviceOption,
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(BuildContext context, String title, {VoidCallback? onViewAll}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
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
                  context.l10n.viewAll,
                  style: TextStyle(color: Colors.grey[400], fontSize: 12, fontWeight: FontWeight.w500),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildDailyRecapsPreview(BuildContext context) {
    final cardHeight = 130.0;
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
                  width: 260,
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
          itemBuilder: (context, index) => _buildSummaryCard(context, _recentSummaries[index], cardHeight),
        ),
      ),
    );
  }

  static const double _cardWidth = 260.0;
  static const double _mapHeight = 60.0;

  Widget _buildSummaryCard(BuildContext context, DailySummary summary, double cardHeight) {
    final hasMap = summary.locations.isNotEmpty;

    return GestureDetector(
      onTap: () {
        MixpanelManager().dailySummaryDetailViewed(summaryId: summary.id, date: summary.date);
        Navigator.push(
          context,
          MaterialPageRoute(builder: (context) => DailySummaryDetailPage(summaryId: summary.id, summary: summary)),
        );
      },
      child: Container(
        width: _cardWidth,
        height: cardHeight,
        margin: const EdgeInsets.only(right: 12),
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(20)),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: Stack(
            children: [
              // Map at bottom
              if (hasMap)
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: _mapHeight,
                  child: _buildCardMap(summary),
                ),
              // Text content at top
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                bottom: hasMap ? _mapHeight : 0,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
                  child: Text(
                    summary.headline,
                    style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              // Date chip overlaying the map at bottom-right
              Positioned(
                bottom: 10,
                right: 10,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(50),
                  ),
                  child: Text(
                    _formatDate(context, summary.date),
                    style: const TextStyle(color: Color(0xFFBBBCC2), fontSize: 11),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCardMap(DailySummary summary) {
    final centerLat = summary.locations.map((l) => l.latitude).reduce((a, b) => a + b) / summary.locations.length;
    final centerLng = summary.locations.map((l) => l.longitude).reduce((a, b) => a + b) / summary.locations.length;

    final markers = summary.locations
        .map((loc) => Marker(
              point: LatLng(loc.latitude, loc.longitude),
              width: 22,
              height: 22,
              child: Container(
                decoration: const BoxDecoration(color: Colors.deepPurple, shape: BoxShape.circle),
                child: const Icon(Icons.location_on, color: Colors.white, size: 13),
              ),
            ))
        .toList();

    return SizedBox(
      width: _cardWidth,
      height: _mapHeight,
      child: IgnorePointer(
        child: FlutterMap(
          options: MapOptions(
            initialCenter: LatLng(centerLat, centerLng),
            initialZoom: 13,
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
              subdomains: const ['a', 'b', 'c', 'd'],
              userAgentPackageName: 'me.omi.app',
              minNativeZoom: 0,
              maxNativeZoom: 19,
              retinaMode: true,
            ),
            MarkerLayer(markers: markers),
          ],
        ),
      ),
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
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (context) => const MemoryGraphPage(trackOpenEvent: false)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: SizedBox(
            height: 180,
            child: IgnorePointer(
              child: MemoryGraphPage(
                embedded: true,
                showAppBar: false,
                showShareButton: false,
                trackOpenEvent: false,
                autoRebuildIfEmpty: false,
                hideRebuildButtonWhenEmpty: true,
                initialZoom: 0.6,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildConversationsPreview(ConversationProvider convoProvider) {
    if (convoProvider.isLoadingConversations && convoProvider.conversations.isEmpty) {
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

    // Use groupedConversations because it has the user's filters already applied
    // (discarded / short / starred / date). conversations.take(3) ignores
    // showDiscardedConversations and would show items that aren't on the
    // conversations page.
    final sortedDates = convoProvider.groupedConversations.keys.toList()..sort((a, b) => b.compareTo(a));
    final recent = <ServerConversation>[];
    for (final date in sortedDates) {
      final list = convoProvider.groupedConversations[date] ?? const [];
      for (final c in list) {
        recent.add(c);
        if (recent.length >= 3) break;
      }
      if (recent.length >= 3) break;
    }
    if (recent.isEmpty) return const SliverToBoxAdapter(child: SizedBox.shrink());

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        childCount: recent.length,
        (context, index) {
          final c = recent[index];
          final dateKey = DateTime(c.createdAt.year, c.createdAt.month, c.createdAt.day);
          return ConversationListItem(
            key: ValueKey(c.id),
            conversation: c,
            date: dateKey,
            conversationIdx: index,
          );
        },
      ),
    );
  }
}
