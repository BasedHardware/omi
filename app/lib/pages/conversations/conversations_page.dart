import 'dart:async';

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
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'widgets/conversations_group_widget.dart';
import 'widgets/conversation_list_item.dart';
import 'widgets/date_list_item.dart';
import 'widgets/empty_conversations.dart';
import 'widgets/recording_list_item.dart';

enum _ConversationListRowKind { topSpacer, dateHeader, conversation, recording, groupSpacer }

typedef _ConversationListRow = ({
  _ConversationListRowKind kind,
  DateTime date,
  bool isFirst,
  ServerConversation? conversation,
  LocalRecording? recording,
  int conversationIndex,
});

typedef _ConversationPageSnapshot = ({
  List<ServerConversation> conversations,
  Map<DateTime, List<ServerConversation>> groupedConversations,
  List<ServerConversation> processingConversations,
  List<LocalRecording> recordings,
  String previousQuery,
  String? selectedFolderId,
  String? selectedSpeakerId,
  DateTime? selectedStartDate,
  DateTime? selectedEndDate,
  bool showStarredOnly,
  bool showDailySummaries,
  bool hasDailySummaries,
  bool isSelectionModeActive,
  bool isLoadingConversations,
  bool isFetchingConversations,
  bool isAwaitingInitialFetchRetry,
  int conversationIdentitySignature,
  int processingIdentitySignature,
  int recordingIdentitySignature,
  int pendingDeleteCount,
});

int _identitySignature(Iterable<Object> values) => Object.hashAll(values.map(identityHashCode));

/// Whether a failed page request should release the scroll request latch so
/// the same server offset can be retried.
bool shouldReleaseConversationLoadMoreLatch({
  required String? currentRequestKey,
  required String requestKey,
  required bool succeeded,
}) =>
    !succeeded && currentRequestKey == requestKey;

String conversationLoadMoreFilterKey({
  required String query,
  required String? folderId,
  required String? speakerId,
  required DateTime? startDate,
  required DateTime? endDate,
  required bool starredOnly,
  required bool discarded,
  required bool shortOnly,
  required int shortThreshold,
}) =>
    [
      query,
      folderId ?? '',
      speakerId ?? '',
      startDate?.toIso8601String() ?? '',
      endDate?.toIso8601String() ?? '',
      starredOnly,
      discarded,
      shortOnly,
      shortThreshold,
    ].join('|');

_ConversationPageSnapshot _conversationPageSnapshot(
  ConversationProvider conversations,
  LocalRecordingsProvider recordings,
) {
  return (
    conversations: conversations.conversations,
    groupedConversations: conversations.groupedConversations,
    processingConversations: conversations.processingConversations,
    recordings: recordings.recordings,
    previousQuery: conversations.previousQuery,
    selectedFolderId: conversations.selectedFolderId,
    selectedSpeakerId: conversations.selectedSpeakerId,
    selectedStartDate: conversations.selectedStartDate,
    selectedEndDate: conversations.selectedEndDate,
    showStarredOnly: conversations.showStarredOnly,
    showDailySummaries: conversations.showDailySummaries,
    hasDailySummaries: conversations.hasDailySummaries,
    isSelectionModeActive: conversations.isSelectionModeActive,
    isLoadingConversations: conversations.isLoadingConversations,
    isFetchingConversations: conversations.isFetchingConversations,
    isAwaitingInitialFetchRetry: conversations.isAwaitingInitialFetchRetry,
    conversationIdentitySignature: _identitySignature(conversations.conversations),
    processingIdentitySignature: _identitySignature(conversations.processingConversations),
    recordingIdentitySignature: _identitySignature(recordings.recordings),
    pendingDeleteCount: conversations.memoriesToDelete.length,
  );
}

List<_ConversationListRow> _buildConversationListRows({
  required List<DateTime> dates,
  required Map<DateTime, List<ServerConversation>> conversationsByDate,
  required Map<DateTime, List<LocalRecording>> recordingsByDate,
}) {
  final rows = <_ConversationListRow>[];
  var hasRenderedDate = false;

  for (var dateIndex = 0; dateIndex < dates.length; dateIndex++) {
    final date = dates[dateIndex];
    final conversations = conversationsByDate[date] ?? const <ServerConversation>[];
    final recordings = recordingsByDate[date] ?? const <LocalRecording>[];
    final entries = buildConversationGroupEntries(conversations: conversations, recordings: recordings);
    final conversationIndexes = <String, int>{
      for (var index = 0; index < conversations.length; index++) conversations[index].id: index,
    };
    if (entries.isEmpty) continue;

    if (!hasRenderedDate) {
      rows.add((
        kind: _ConversationListRowKind.topSpacer,
        date: date,
        isFirst: true,
        conversation: null,
        recording: null,
        conversationIndex: -1,
      ));
    }
    rows.add((
      kind: _ConversationListRowKind.dateHeader,
      date: date,
      isFirst: !hasRenderedDate,
      conversation: null,
      recording: null,
      conversationIndex: -1,
    ));

    for (final entry in entries) {
      final conversation = entry.conversation;
      final recording = entry.recording;
      if (conversation != null) {
        rows.add((
          kind: _ConversationListRowKind.conversation,
          date: date,
          isFirst: false,
          conversation: conversation,
          recording: null,
          conversationIndex: conversationIndexes[conversation.id] ?? -1,
        ));
      } else {
        rows.add((
          kind: _ConversationListRowKind.recording,
          date: date,
          isFirst: false,
          conversation: null,
          recording: recording,
          conversationIndex: -1,
        ));
      }
    }

    rows.add((
      kind: _ConversationListRowKind.groupSpacer,
      date: date,
      isFirst: false,
      conversation: null,
      recording: null,
      conversationIndex: -1,
    ));
    hasRenderedDate = true;
  }

  return rows;
}

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
  String? _loadMoreFilterKey;
  String? _lastLoadMoreRequestKey;
  bool _isBootstrapping = true;

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
      try {
        if (conversationProvider.conversations.isEmpty) {
          await conversationProvider.getInitialConversations();
        } else {
          // Still check for daily summaries even if conversations are cached
          _scheduleDeferred(conversationProvider.checkHasDailySummaries);
        }
      } finally {
        if (mounted) setState(() => _isBootstrapping = false);
      }

      if (!mounted) return;

      // Keep filesystem scanning off the first navigation/scroll frame.
      _scheduleDeferred(context.read<LocalRecordingsProvider>().refresh);

      // Load folders for folder tabs
      final folderProvider = context.read<FolderProvider>();
      if (folderProvider.folders.isEmpty) {
        _scheduleDeferred(folderProvider.loadFolders);
      }

      // Check if we should show the app review prompt for first conversation
      if (mounted && conversationProvider.conversations.isNotEmpty) {
        _scheduleDeferred(
          () => _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: true),
        );
      }
    });
  }

  void _scheduleDeferred(Future<void> Function() operation) {
    unawaited(
      Future<void>.delayed(const Duration(milliseconds: 200), () async {
        if (!mounted) return;
        try {
          await operation();
        } catch (error, stackTrace) {
          Logger.error('Deferred conversations-page work failed: $error\n$stackTrace');
        }
      }),
    );
  }

  bool _requestMoreIfNeeded(ConversationProvider provider) {
    if (provider.isLoadingConversations) return false;

    final filterKey = conversationLoadMoreFilterKey(
      query: provider.previousQuery,
      folderId: provider.selectedFolderId,
      speakerId: provider.selectedSpeakerId,
      startDate: provider.selectedStartDate,
      endDate: provider.selectedEndDate,
      starredOnly: provider.showStarredOnly,
      discarded: provider.showDiscardedConversations,
      shortOnly: provider.showShortConversations,
      shortThreshold: provider.shortConversationThreshold,
    );
    if (_loadMoreFilterKey != filterKey) {
      _loadMoreFilterKey = filterKey;
      _lastLoadMoreRequestKey = null;
    }

    final String pageOrCount;
    final isSearch = provider.previousQuery.isNotEmpty || provider.selectedSpeakerId != null;
    if (isSearch) {
      if (provider.totalSearchPages <= provider.currentSearchPage) return false;
      pageOrCount = 'page:${provider.currentSearchPage}';
    } else {
      if (!provider.hasMoreConversations) return false;
      pageOrCount = 'offset:${provider.conversationServerOffset}';
    }

    final requestKey = '$filterKey|$pageOrCount';
    if (_lastLoadMoreRequestKey == requestKey) return false;
    _lastLoadMoreRequestKey = requestKey;

    if (isSearch) {
      unawaited(provider.searchMoreConversations());
    } else {
      unawaited(provider.getMoreConversationsFromServer().then((succeeded) {
        if (mounted &&
            shouldReleaseConversationLoadMoreLatch(
              currentRequestKey: _lastLoadMoreRequestKey,
              requestKey: requestKey,
              succeeded: succeeded,
            )) {
          // A failed page fetch leaves the server cursor unchanged; release
          // the latch so the next scroll can retry the same offset.
          _lastLoadMoreRequestKey = null;
        }
      }));
    }
    return true;
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

  // True when any conversation filter is active. When filters are on, the
  // `conversations` list reflects filtered server results (e.g. an empty list
  // when "Starred" + a folder yield no matches). Without this, the title and
  // folder-tab chips would hide on empty filtered results, leaving no way to
  // clear filters short of restarting the app.
  bool _hasActiveFilter(ConversationProvider provider) {
    return provider.showStarredOnly || provider.selectedFolderId != null || provider.selectedStartDate != null;
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
                    colors: [Colors.deepPurple.withValues(alpha: 0.35), Colors.deepPurple.withValues(alpha: 0.0)],
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
            style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.3),
          ),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 280),
            child: Text(
              'Conversations you record show up here. Tap a tile on the home tab to start your first one.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 15, height: 1.5),
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
    return Selector2<ConversationProvider, LocalRecordingsProvider, _ConversationPageSnapshot>(
      selector: (_, conversationProvider, recordingsProvider) =>
          _conversationPageSnapshot(conversationProvider, recordingsProvider),
      builder: (context, snapshot, child) {
        final convoProvider = context.read<ConversationProvider>();
        // Unsynced local recordings (batch/offline mode) shown inline with conversations,
        // grouped into the same date buckets. Only in the default view (no search/folder/
        // starred/daily-summaries filter).
        final bool showRecordings = convoProvider.previousQuery.isEmpty &&
            convoProvider.selectedFolderId == null &&
            !convoProvider.showStarredOnly &&
            !convoProvider.showDailySummaries;
        final recordingsByDate = <DateTime, List<LocalRecording>>{};
        if (showRecordings) {
          // Batch/offline-mode recordings captured locally — a separate subsystem
          // from device offline-sync (which lives on the Sync page).
          for (final rec in snapshot.recordings) {
            final dt = DateTime.fromMillisecondsSinceEpoch(rec.timerStart * 1000);
            final day = DateTime(dt.year, dt.month, dt.day);
            (recordingsByDate[day] ??= <LocalRecording>[]).add(rec);
          }
        }
        final bool hasRecordings = recordingsByDate.isNotEmpty;
        final bool isWaitingForInitialData = _isBootstrapping && snapshot.conversations.isEmpty && !hasRecordings;
        final bool isShowingConversationSkeleton = isWaitingForInitialData ||
            convoProvider.isLoadingConversations ||
            convoProvider.isFetchingConversations ||
            convoProvider.isAwaitingInitialFetchRetry;
        final mergedDates = <DateTime>{...convoProvider.groupedConversations.keys, ...recordingsByDate.keys}.toList()
          ..sort((a, b) => b.compareTo(a));
        final conversationRows = _buildConversationListRows(
          dates: mergedDates,
          conversationsByDate: convoProvider.groupedConversations,
          recordingsByDate: recordingsByDate,
        );

        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            _lastLoadMoreRequestKey = null;
            Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
            // Refresh goals widget
            _goalsWidgetKey.currentState?.refresh();
            _refreshGoals();
            await Future.wait([
              convoProvider.getInitialConversations(),
              Provider.of<FolderProvider>(context, listen: false).loadFolders(),
              Provider.of<LocalRecordingsProvider>(context, listen: false).refresh(),
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
              Selector<HomeProvider, bool>(
                selector: (_, homeProvider) => homeProvider.showConvoSearchBar,
                builder: (context, showConvoSearchBar, _) {
                  bool shouldShowSearchBar = showConvoSearchBar || convoProvider.previousQuery.isNotEmpty;
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
              Selector<HomeProvider, bool>(
                selector: (_, homeProvider) => homeProvider.showConvoSearchBar,
                builder: (context, showConvoSearchBar, _) {
                  final isSearchActive = showConvoSearchBar || convoProvider.previousQuery.isNotEmpty;
                  final hasCalendarFilter = convoProvider.selectedStartDate != null;
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
                        if (showGoals)
                          RepaintBoundary(
                            child: GoalsWidget(key: _goalsWidgetKey, onRefresh: _refreshGoals),
                          ),
                      ],
                    ),
                  );
                },
              ),

              // Section header - show "Daily Recaps" or "Conversations" with optional recording pill.
              // Hidden entirely when the user has zero non-discarded
              // conversations (and isn't on the Daily Recaps view) — those
              // users get the empty-state hero below instead.
              if (convoProvider.showDailySummaries ||
                  _nonDiscardedConversationCount(convoProvider) > 0 ||
                  isShowingConversationSkeleton ||
                  _hasActiveFilter(convoProvider))
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
              // has no conversations yet (matches the title). Keep chips
              // visible whenever a filter is active so the user can always
              // clear it, even when the filtered result is empty.
              if (!convoProvider.showDailySummaries &&
                  (_nonDiscardedConversationCount(convoProvider) > 0 ||
                      isShowingConversationSkeleton ||
                      _hasActiveFilter(convoProvider)))
                Consumer<FolderProvider>(
                  builder: (context, folderProvider, _) {
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
              else if (_nonDiscardedConversationCount(convoProvider) == 0 &&
                  !hasRecordings &&
                  !isShowingConversationSkeleton &&
                  !_hasActiveFilter(convoProvider))
                // Friendly hero for brand-new users with zero conversations —
                // matches the polished Tasks empty state.
                SliverFillRemaining(hasScrollBody: false, child: Center(child: _buildNoConversationsHero(context)))
              else if (convoProvider.groupedConversations.isEmpty && !hasRecordings && !isShowingConversationSkeleton)
                SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 32.0),
                      child: EmptyConversationsWidget(isStarredFilterActive: convoProvider.showStarredOnly),
                    ),
                  ),
                )
              else if (convoProvider.groupedConversations.isEmpty && !hasRecordings && isShowingConversationSkeleton)
                _buildLoadingShimmer()
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(childCount: conversationRows.length + 1, (context, index) {
                    if (index == conversationRows.length) {
                      Logger.debug('loading more conversations');
                      if (convoProvider.isLoadingConversations) {
                        return _buildLoadMoreShimmer();
                      }
                      // widget.loadMoreMemories(); // CALL this only when visible
                      return VisibilityDetector(
                        key: const Key('conversations-key'),
                        onVisibilityChanged: (visibilityInfo) {
                          if (visibilityInfo.visibleFraction > 0) {
                            _requestMoreIfNeeded(context.read<ConversationProvider>());
                          }
                        },
                        child: const SizedBox(height: 20, width: double.maxFinite),
                      );
                    }

                    final row = conversationRows[index];
                    switch (row.kind) {
                      case _ConversationListRowKind.topSpacer:
                        return const SizedBox(height: 10);
                      case _ConversationListRowKind.dateHeader:
                        return DateListItem(
                          key: ValueKey('date_${row.date.toIso8601String()}'),
                          date: row.date,
                          isFirst: row.isFirst,
                        );
                      case _ConversationListRowKind.conversation:
                        return ConversationListItem(
                          key: ValueKey(row.conversation!.id),
                          conversation: row.conversation!,
                          conversationIdx: row.conversationIndex,
                          date: row.date,
                        );
                      case _ConversationListRowKind.recording:
                        return RecordingListItem(key: ValueKey('rec_${row.recording!.id}'), recording: row.recording!);
                      case _ConversationListRowKind.groupSpacer:
                        return const SizedBox(height: 10);
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
