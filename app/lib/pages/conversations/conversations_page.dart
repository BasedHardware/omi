import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/ui/ui.dart';

import 'package:omi/widgets/home_bottom_bar.dart';

String _conversationDateRangeLabel(BuildContext context, DateTime start, DateTime? end) {
  final dates = OmiDateFormat.of(context);
  if (end == null || (start.year == end.year && start.month == end.month && start.day == end.day)) {
    return dates.date(start);
  }
  return '${dates.date(start)} – ${dates.date(end)}';
}

enum _ConversationListRowKind {
  topSpacer,
  dateHeader,
  processing,
  conversation,
  recording,
  groupSpacer,
}

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
  bool isSelectionModeActive,
  bool isLoadingConversations,
  bool isFetchingConversations,
  bool isAwaitingInitialFetchRetry,
  ApiViewPhase apiViewPhase,
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
    isSelectionModeActive: conversations.isSelectionModeActive,
    isLoadingConversations: conversations.isLoadingConversations,
    isFetchingConversations: conversations.isFetchingConversations,
    isAwaitingInitialFetchRetry: conversations.isAwaitingInitialFetchRetry,
    apiViewPhase: conversations.apiViewState.phase,
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
  Map<DateTime, ServerConversation> processingByDate = const {},
}) {
  final rows = <_ConversationListRow>[];
  var hasRenderedDate = false;

  for (var dateIndex = 0; dateIndex < dates.length; dateIndex++) {
    final date = dates[dateIndex];
    final conversations = conversationsByDate[date] ?? const <ServerConversation>[];
    final recordings = recordingsByDate[date] ?? const <LocalRecording>[];
    final processing = processingByDate[date];
    final entries = buildConversationGroupEntries(conversations: conversations, recordings: recordings);
    final conversationIndexes = <String, int>{
      for (var index = 0; index < conversations.length; index++) conversations[index].id: index,
    };
    if (entries.isEmpty && processing == null) continue;

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

    // Process Now belongs to the list, above the day where the completed conversation lands.
    if (processing != null) {
      rows.add((
        kind: _ConversationListRowKind.processing,
        date: date,
        isFirst: false,
        conversation: processing,
        recording: null,
        conversationIndex: -1,
      ));
    }

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

bool _isLockedRow(List<_ConversationListRow> rows, int index) =>
    index >= 0 &&
    index < rows.length &&
    rows[index].kind == _ConversationListRowKind.conversation &&
    rows[index].conversation!.isLocked;

/// For a locked conversation row in a run of two or more consecutive locked rows (one day): the
/// whole run when [index] starts it, an empty list when an earlier row already drew it, and null
/// for any other row, which draws itself.
List<ServerConversation>? _lockedRunAt(List<_ConversationListRow> rows, int index) {
  if (!_isLockedRow(rows, index)) return null;
  if (_isLockedRow(rows, index - 1)) return const [];
  var end = index + 1;
  while (_isLockedRow(rows, end)) {
    end++;
  }
  if (end - index < 2) return null;
  return [for (var i = index; i < end; i++) rows[i].conversation!];
}

/// Home: the live capture row, the Daily Recaps row, then every conversation, newest first, loading
/// more as it scrolls. Search, folders, starred and places live in the search overlay the header's
/// search button opens, so this list is never filtered in place.
class ConversationsPage extends StatefulWidget {
  const ConversationsPage({super.key, this.requestInitialLoad = true, this.loadRecaps});

  /// Production stays true. Widget tests that already call
  /// [ConversationProvider.getInitialConversations] inside `runAsync` pass
  /// false so initState does not queue loopback I/O on the fake-async clock.
  final bool requestInitialLoad;

  /// Injectable for tests and the visual audit; defaults to the recaps endpoint.
  final RecentRecapsLoader? loadRecaps;

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<HomeDailyRecapsState> _recapsKey = GlobalKey<HomeDailyRecapsState>();
  String? _loadMoreFilterKey;
  String? _lastLoadMoreRequestKey;
  bool _isBootstrapping = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final conversationProvider = context.read<ConversationProvider>();
      try {
        if (widget.requestInitialLoad && conversationProvider.conversations.isEmpty) {
          await conversationProvider.getInitialConversations();
        } else if (widget.requestInitialLoad) {
          // Still check for daily summaries even if conversations are cached
          _scheduleDeferred(conversationProvider.checkHasDailySummaries);
        }
      } finally {
        if (mounted) setState(() => _isBootstrapping = false);
      }

      if (!mounted) return;

      // Keep filesystem scanning off the first navigation/scroll frame.
      _scheduleDeferred(context.read<LocalRecordingsProvider>().refresh);
    });
  }

  /// Deferred work still waiting to start; cancelled on dispose so Home leaves no timer behind.
  final List<Timer> _deferred = [];

  void _scheduleDeferred(Future<void> Function() operation) {
    late final Timer timer;
    timer = Timer(const Duration(milliseconds: 200), () async {
      _deferred.remove(timer);
      if (!mounted) return;
      try {
        await operation();
      } catch (error, stackTrace) {
        Logger.error('Deferred conversations-page work failed: $error\n$stackTrace');
      }
    });
    _deferred.add(timer);
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
      unawaited(
        provider.getMoreConversationsFromServer().then((succeeded) {
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
        }),
      );
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
    for (final timer in _deferred) {
      timer.cancel();
    }
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
            baseColor: OmiColors.surface1,
            highlightColor: OmiColors.surface3,
            child: Container(
              width: 100,
              height: 16,
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(8)),
            ),
          ),
          const SizedBox(height: 12),
          // Conversation items shimmer
          ...List.generate(
            3,
            (index) => Padding(
              padding: const EdgeInsets.only(bottom: 16.0),
              child: ShimmerWithTimeout(
                baseColor: OmiColors.surface1,
                highlightColor: OmiColors.surface3,
                child: Container(
                  height: 80,
                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(12)),
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
        baseColor: OmiColors.surface1,
        highlightColor: OmiColors.surface3,
        child: Container(
          height: 60,
          margin: const EdgeInsets.symmetric(horizontal: 16.0),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(12)),
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
            !convoProvider.showStarredOnly;
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
        final bool hasProcessingConversations = snapshot.processingConversations.isNotEmpty;
        final processingNewest = newestProcessingConversation(snapshot.processingConversations);
        final processingByDate = <DateTime, ServerConversation>{
          if (processingNewest != null)
            conversationLocalDayKey(processingNewest.startedAt ?? processingNewest.createdAt): processingNewest,
        };
        final apiPhase = snapshot.apiViewPhase;
        final bool showTypedStatus = apiPhase == ApiViewPhase.error ||
            apiPhase == ApiViewPhase.locked ||
            apiPhase == ApiViewPhase.terminal ||
            apiPhase == ApiViewPhase.authenticationRequired ||
            apiPhase == ApiViewPhase.empty;
        final bool isWaitingForInitialData = _isBootstrapping && snapshot.conversations.isEmpty && !hasRecordings;
        final bool isShowingConversationSkeleton = isWaitingForInitialData ||
            convoProvider.isLoadingConversations ||
            convoProvider.isFetchingConversations ||
            convoProvider.isAwaitingInitialFetchRetry;
        final mergedDates = <DateTime>{
          ...convoProvider.groupedConversations.keys,
          ...recordingsByDate.keys,
          ...processingByDate.keys,
        }.toList()
          ..sort((a, b) => b.compareTo(a));
        final conversationRows = _buildConversationListRows(
          dates: mergedDates,
          conversationsByDate: convoProvider.groupedConversations,
          recordingsByDate: recordingsByDate,
          processingByDate: processingByDate,
        );

        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            _lastLoadMoreRequestKey = null;
            Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
            await Future.wait([
              convoProvider.getInitialConversations(),
              Provider.of<LocalRecordingsProvider>(context, listen: false).refresh(),
              if (_recapsKey.currentState != null) _recapsKey.currentState!.refresh(),
            ]);
          },
          color: OmiColors.onAccent,
          backgroundColor: OmiColors.accent,
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // The live capture row: recording, a call, or a conversation being captured.
              const SliverToBoxAdapter(child: ConversationCaptureWidget(showsCall: true)),
              const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
              const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
              const SliverToBoxAdapter(child: SpeakerTagPromptCard()),
              const SliverToBoxAdapter(child: CaptureRecoveryBanner()),
              SliverToBoxAdapter(
                child: widget.loadRecaps == null
                    ? HomeDailyRecaps(key: _recapsKey)
                    : HomeDailyRecaps(key: _recapsKey, load: widget.loadRecaps!),
              ),
              // Typed HTTP status precedes empty/loading/hero so an outage is
              // never the new-account empty state. Unset (data) keeps production.
              if (showTypedStatus &&
                  snapshot.conversations.isEmpty &&
                  !hasProcessingConversations &&
                  !hasRecordings &&
                  !_hasActiveFilter(convoProvider))
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: ConversationApiStatus(provider: convoProvider)),
                )
              else if (_nonDiscardedConversationCount(convoProvider) == 0 &&
                  !hasProcessingConversations &&
                  !hasRecordings &&
                  !isShowingConversationSkeleton &&
                  !_hasActiveFilter(convoProvider))
                // Friendly hero for brand-new users with zero conversations —
                // matches the polished Tasks empty state.
                const SliverFillRemaining(hasScrollBody: false, child: Center(child: NoConversationsHero()))
              else if (convoProvider.groupedConversations.isEmpty &&
                  !hasRecordings &&
                  !hasProcessingConversations &&
                  !isShowingConversationSkeleton)
                SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 32.0),
                      child: EmptyConversationsWidget(
                        isStarredFilterActive: convoProvider.showStarredOnly,
                        dateFilterLabel: convoProvider.selectedStartDate == null
                            ? null
                            : _conversationDateRangeLabel(
                                context,
                                convoProvider.selectedStartDate!,
                                convoProvider.selectedEndDate,
                              ),
                      ),
                    ),
                  ),
                )
              else if (convoProvider.groupedConversations.isEmpty &&
                  !hasRecordings &&
                  !hasProcessingConversations &&
                  isShowingConversationSkeleton)
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
                      case _ConversationListRowKind.processing:
                        return ProcessingConversationWidget(
                          key: ValueKey('processing_${row.conversation!.id}'),
                          conversation: row.conversation!,
                        );
                      case _ConversationListRowKind.conversation:
                        // Consecutive locked rows share one frosted card and one upgrade action;
                        // the run's first row draws it and the rest of the run draws nothing.
                        final lockedRun = _lockedRunAt(conversationRows, index);
                        if (lockedRun != null) {
                          if (lockedRun.isEmpty) return const SizedBox.shrink();
                          return LockedConversationRun(
                            key: ValueKey('locked_run_${row.conversation!.id}'),
                            conversations: lockedRun,
                            date: row.date,
                          );
                        }
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
              // Clears the floating chat bar, or the taller merge action bar that replaces it in
              // selection mode; both sit on top of the same system inset.
              SliverToBoxAdapter(
                child: SizedBox(
                  height: convoProvider.isSelectionModeActive
                      ? 160 + homeBottomInset(context)
                      : homeChatBarClearance(context),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
