import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/today_tasks_widget.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
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

  // The capturing page only renders transcript/photos that are already
  // streaming in — it does not start the mic itself. So opening it without
  // first kicking off phone-mic recording leaves the user stuck on the
  // "waiting for transcript or photos" placeholder forever. Mirror the
  // proven start path (battery_info_widget._startRecording).
  Future<void> _startPhoneRecording(BuildContext context) async {
    // No haptic here — the option() wrapper already fires lightImpact() on tap;
    // a mediumImpact() on top of it double-vibrates on a single tap.
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.recordingState == RecordingState.initialising) return;
    if (captureProvider.recordingState != RecordingState.record) {
      await captureProvider.streamRecording();
      PlatformManager.instance.analytics.phoneMicRecordingStarted();
    }
    // A phone-mic Transcribe Later (batch) session has no live transcript — the
    // conversations-list batch card is its surface, so skip the capturing page
    // (same as BLE batch). Surface the auto offline fallback once.
    if (captureProvider.isPhoneMicBatchRecording) {
      if (SharedPreferencesUtil().phoneBatchAuto && context.mounted) {
        AppSnackbar.showSnackbar(context.l10n.phoneMicOfflineFallbackMessage);
      }
      return;
    }
    if (!context.mounted) return;
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ConversationCapturingPage(topConversationId: captureProvider.topConversationId),
      ),
    );
  }

  Widget _buildGetStartedOptions(BuildContext context) {
    Widget option({required IconData icon, required String label, required VoidCallback onTap}) {
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
              width: 120,
              child: Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500, height: 1.2),
              ),
            ),
          ],
        ),
      );
    }

    final phoneOption = option(
      icon: Icons.mic_rounded,
      label: 'Record with Phone',
      onTap: () => _startPhoneRecording(context),
    );
    final callOption = option(
      icon: Icons.phone_in_talk_rounded,
      label: 'Record Call',
      onTap: () {
        Navigator.push(context, MaterialPageRoute(builder: (_) => const PhoneCallsPage()));
      },
    );
    final deviceOption = option(
      icon: Icons.bluetooth_searching_rounded,
      label: 'Connect Device',
      onTap: () {
        Navigator.push(context, MaterialPageRoute(builder: (_) => const DeviceSelectionPage()));
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
          Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [callOption, deviceOption]),
        ],
      ),
    );
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
}
