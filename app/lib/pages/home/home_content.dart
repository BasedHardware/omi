import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/home/widgets/day_header.dart';
import 'package:omi/pages/home/widgets/day_timeline_entry.dart';
import 'package:omi/pages/onboarding/device_selection.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home is one day at a time: where you were, what the day was about, the
/// conversations in order, and the tasks each one produced.
class HomeContentPage extends StatefulWidget {
  const HomeContentPage({super.key});

  @override
  State<HomeContentPage> createState() => HomeContentPageState();
}

class HomeContentPageState extends State<HomeContentPage> with AutomaticKeepAliveClientMixin {
  /// Days the user can page back through before the timeline stops loading more.
  static const int _maxPagesPerDayJump = 5;

  final ScrollController _scrollController = ScrollController();
  final Map<String, DailySummary> _summariesByDate = {};

  DateTime _selectedDay = _startOfToday();
  bool _loadingOlderDays = false;
  bool _shortConversationsExpanded = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSummaries());
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  static DateTime _startOfToday() {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day);
  }

  static String _dateKey(DateTime day) {
    final month = day.month.toString().padLeft(2, '0');
    final dayOfMonth = day.day.toString().padLeft(2, '0');
    return '${day.year}-$month-$dayOfMonth';
  }

  Future<void> _loadSummaries() async {
    final summaries = await getDailySummaries(limit: 30, offset: 0);
    if (!mounted) return;
    setState(() {
      _summariesByDate
        ..clear()
        ..addEntries(summaries.where((s) => s.date.isNotEmpty).map((s) => MapEntry(s.date, s)));
    });
  }

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0.0, duration: const Duration(milliseconds: 500), curve: Curves.easeOutCubic);
    }
  }

  void _goToDay(DateTime day) {
    if (day.isAfter(_startOfToday())) return;
    HapticFeedback.selectionClick();
    setState(() {
      _selectedDay = day;
      _shortConversationsExpanded = false;
    });
    if (_scrollController.hasClients) _scrollController.jumpTo(0);
    unawaited(_loadDayIfNeeded(day));
  }

  /// Conversations arrive newest-first in pages. Stepping back past the oldest
  /// loaded day pulls more pages so an older day isn't shown as empty just
  /// because it hasn't been fetched yet.
  Future<void> _loadDayIfNeeded(DateTime day) async {
    final provider = context.read<ConversationProvider>();
    if (_isDayLoaded(provider, day) || !provider.hasMoreConversations) return;

    setState(() => _loadingOlderDays = true);
    var pages = 0;
    while (mounted && pages++ < _maxPagesPerDayJump && !_isDayLoaded(provider, day) && provider.hasMoreConversations) {
      if (!await provider.getMoreConversationsFromServer()) break;
    }
    if (mounted) setState(() => _loadingOlderDays = false);
  }

  bool _isDayLoaded(ConversationProvider provider, DateTime day) {
    if (provider.conversations.isEmpty) return false;
    // The list is sorted newest-first, so the last entry is the oldest one the
    // client holds: everything down to its day has been fetched.
    final oldest = provider.conversations.last;
    return !conversationLocalDayKey(oldest.startedAt ?? oldest.createdAt).isAfter(day);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer2<ConversationProvider, ActionItemsProvider>(
      builder: (context, convoProvider, tasksProvider, child) {
        final day = _selectedDay;
        final dayConversations = _conversationsOn(convoProvider, day);
        final highlights = <ServerConversation>[];
        final shortOnes = <ServerConversation>[];
        for (final conversation in dayConversations) {
          final isShort =
              conversation.discarded || conversation.getDurationInSeconds() < convoProvider.shortConversationThreshold;
          (isShort ? shortOnes : highlights).add(conversation);
        }
        final tasksByConversation = _tasksByConversation(tasksProvider);
        final summary = _summariesByDate[_dateKey(day)];
        final isNewUser = convoProvider.conversations.isEmpty &&
            !convoProvider.isLoadingConversations &&
            !convoProvider.isFetchingConversations &&
            !convoProvider.isAwaitingInitialFetchRetry;

        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            await Future.wait([
              convoProvider.getInitialConversations(),
              tasksProvider.fetchActionItems(),
              _loadSummaries(),
            ]);
          },
          color: Colors.white,
          backgroundColor: const Color(0xFF1F1F25),
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              const SliverToBoxAdapter(child: ConversationCaptureWidget()),
              SliverToBoxAdapter(
                child: DayHeader(
                  day: day,
                  conversations: dayConversations,
                  headline: summary?.headline,
                  canGoForward: day.isBefore(_startOfToday()),
                  onPreviousDay: () => _goToDay(DateTime(day.year, day.month, day.day - 1)),
                  onNextDay: () => _goToDay(DateTime(day.year, day.month, day.day + 1)),
                  onHeadlineTap: summary == null ? null : () => _openSummary(summary),
                ),
              ),
              if (isNewUser)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 160),
                    child: Center(child: _buildGetStartedOptions(context)),
                  ),
                )
              else ...[
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    childCount: highlights.length,
                    (context, index) => _buildEntry(highlights[index], tasksByConversation, tasksProvider),
                  ),
                ),
                if (shortOnes.isNotEmpty) SliverToBoxAdapter(child: _buildShortConversationsToggle(shortOnes.length)),
                if (_shortConversationsExpanded)
                  SliverList(
                    delegate: SliverChildBuilderDelegate(
                      childCount: shortOnes.length,
                      (context, index) =>
                          _buildEntry(shortOnes[index], tasksByConversation, tasksProvider, dimmed: true),
                    ),
                  ),
                if (dayConversations.isEmpty && !_loadingOlderDays) SliverToBoxAdapter(child: _buildEmptyDay(context)),
                if (_loadingOlderDays)
                  const SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 32),
                      child: Center(
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white24),
                        ),
                      ),
                    ),
                  ),
                // Room for the floating chat bar and the bottom nav.
                const SliverToBoxAdapter(child: SizedBox(height: 160)),
              ],
            ],
          ),
        );
      },
    );
  }

  List<ServerConversation> _conversationsOn(ConversationProvider provider, DateTime day) {
    final conversations = provider.conversations
        .where((conversation) => conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt) == day)
        .toList();
    // The day reads top to bottom the way it was lived.
    conversations.sort((a, b) => (a.startedAt ?? a.createdAt).compareTo(b.startedAt ?? b.createdAt));
    return conversations;
  }

  Map<String, List<ActionItemWithMetadata>> _tasksByConversation(ActionItemsProvider provider) {
    final grouped = <String, List<ActionItemWithMetadata>>{};
    for (final task in provider.actionItems) {
      final conversationId = task.conversationId;
      if (conversationId == null || conversationId.isEmpty) continue;
      grouped.putIfAbsent(conversationId, () => []).add(task);
    }
    return grouped;
  }

  Widget _buildEntry(
    ServerConversation conversation,
    Map<String, List<ActionItemWithMetadata>> tasksByConversation,
    ActionItemsProvider tasksProvider, {
    bool dimmed = false,
  }) {
    return DayTimelineEntry(
      key: ValueKey(conversation.id),
      conversation: conversation,
      tasks: tasksByConversation[conversation.id] ?? const [],
      dimmed: dimmed,
      onTap: () => _openConversation(conversation),
      onToggleTask: (task) => tasksProvider.updateActionItemState(task, !task.completed),
    );
  }

  Widget _buildShortConversationsToggle(int count) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        HapticFeedback.selectionClick();
        setState(() => _shortConversationsExpanded = !_shortConversationsExpanded);
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(82, 22, 24, 6),
        child: Text(
          context.l10n.shortConversationsCount(count),
          style: TextStyle(color: Colors.white.withValues(alpha: 0.35), fontSize: 14),
        ),
      ),
    );
  }

  Widget _buildEmptyDay(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 40, 24, 0),
      child: Center(
        child: Text(
          context.l10n.noConversationsYet,
          style: TextStyle(color: Colors.white.withValues(alpha: 0.3), fontSize: 15),
        ),
      ),
    );
  }

  Future<void> _openConversation(ServerConversation conversation) async {
    HapticFeedback.selectionClick();
    final provider = context.read<ConversationProvider>();
    provider.onConversationTap(conversation.id);
    await routeToPage(context, ConversationDetailPage(conversation: conversation));
  }

  Future<void> _openSummary(DailySummary summary) async {
    PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: summary.id, date: summary.date);
    final result = await Navigator.push<dynamic>(
      context,
      MaterialPageRoute(builder: (context) => DailySummaryDetailPage(summaryId: summary.id, summary: summary)),
    );
    if (!mounted) return;
    if (result is Map && result['deleted'] == true) {
      setState(() => _summariesByDate.remove(summary.date));
    }
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
                color: const Color(0xFF1F1F25),
                border: Border.all(color: Colors.white.withValues(alpha: 0.12), width: 1),
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
}
