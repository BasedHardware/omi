// Home's conversation list. One model (`buildHome`, home/home_model.dart) decides every row; this
// page reads the providers into its inputs, draws each row kind with one widget, and owns paging,
// pull-to-refresh and the v3 live polling.
//
// The client is v3 only (David, 2026-11-27, SCA-5226): there is no card feed, no episode
// projection and no legacy processing row on Home.
//
// The page stays alive across tab switches (AutomaticKeepAliveClientMixin), so scroll position and
// pagination survive background sync mutations; load-more state is keyed by the active filter and
// resets deliberately on filter change.
import 'dart:async';

import 'package:clock/clock.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/conversations/home/home_live_rows.dart';
import 'package:omi/pages/conversations/home/home_locked_row.dart';
import 'package:omi/pages/conversations/home/home_model.dart';
import 'package:omi/pages/conversations/home/home_prompt_slot.dart';
import 'package:omi/pages/conversations/home_rows_health.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_words_log.dart';
import 'package:omi/services/live_preview/speech_after_end.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/local_day_rollover.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/home_bottom_bar.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

String _conversationDateRangeLabel(BuildContext context, DateTime start, DateTime? end) {
  final dates = OmiDateFormat.of(context);
  if (end == null || (start.year == end.year && start.month == end.month && start.day == end.day)) {
    return dates.date(start);
  }
  return '${dates.date(start)} – ${dates.date(end)}';
}

/// Whether a failed page request should release the scroll request latch so
/// the same server offset can be retried.
/// Everything Home's list reads from the conversation and recording providers. Lists are compared
/// by the identity of their members, so an in-place replacement (a completion landing) rebuilds the
/// list while an unrelated notify does not.
typedef _HomeSnapshot = ({
  int conversations,
  int grouped,
  int processing,
  int recordings,
  bool showsPendingFinishOnHome,
  bool hasActiveHomeFilter,
  bool showStarredOnly,
  DateTime? selectedStartDate,
  DateTime? selectedEndDate,
  bool isSelectionModeActive,
  bool isLoadingConversations,
  bool isFetchingConversations,
  bool isAwaitingInitialFetchRetry,
  ApiViewPhase apiViewPhase,
  int pendingDeleteCount,
  HomeEmptyExplanation homeEmptyExplanation,
  bool loadMoreFailed,
  bool hasMoreConversations,
});

int _identitySignature(Iterable<Object> values) => Object.hashAll(values.map(identityHashCode));

_HomeSnapshot _homeSnapshot(ConversationProvider c, LocalRecordingsProvider r) => (
      conversations: _identitySignature(c.conversations),
      grouped: Object.hashAll(
          c.groupedConversations.entries.map((e) => Object.hash(e.key, Object.hashAll(e.value.map(identityHashCode))))),
      processing: _identitySignature(c.processingConversations),
      recordings: _identitySignature(r.recordings),
      showsPendingFinishOnHome: c.showsPendingFinishOnHome,
      hasActiveHomeFilter: c.hasActiveHomeFilter,
      showStarredOnly: c.showStarredOnly,
      selectedStartDate: c.selectedStartDate,
      selectedEndDate: c.selectedEndDate,
      isSelectionModeActive: c.isSelectionModeActive,
      isLoadingConversations: c.isLoadingConversations,
      isFetchingConversations: c.isFetchingConversations,
      isAwaitingInitialFetchRetry: c.isAwaitingInitialFetchRetry,
      apiViewPhase: c.apiViewState.phase,
      pendingDeleteCount: c.memoriesToDelete.length,
      homeEmptyExplanation: c.homeEmptyExplanation,
      loadMoreFailed: c.loadMoreFailed,
      hasMoreConversations: c.hasMoreConversations,
    );

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

/// Home: one prompt at most, then every day newest first, its live row and rows, loading more as it
/// scrolls. Search, folders, starred and places live in the search overlay the header's search
/// button opens.
class ConversationsPage extends StatefulWidget {
  const ConversationsPage({super.key, this.requestInitialLoad = true, this.pendingWork, this.openDaySummary});

  /// Production stays true. Widget tests that already call
  /// [ConversationProvider.getInitialConversations] inside `runAsync` pass
  /// false so initState does not queue loopback I/O on the fake-async clock.
  final bool requestInitialLoad;

  /// Test seam for a past day header's tap.
  final DaySummaryOpener? openDaySummary;

  /// Injectable for tests; defaults to [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  final ScrollController _scrollController = ScrollController();

  /// Follow-up pages asked for without a new scroll since the reader last moved; see
  /// [_requestMoreIfNeeded].
  int _autoLoadMorePages = 0;
  static const _maxAutoLoadMorePages = 4;

  void _onScroll({bool fromScroll = true}) {
    if (!_scrollController.hasClients) return;
    if (fromScroll) _autoLoadMorePages = 0;
    final position = _scrollController.position;
    if (position.extentAfter < position.viewportDimension * 2) {
      _requestMoreIfNeeded(context.read<ConversationProvider>());
    }
  }

  String? _loadMoreFilterKey;
  String? _lastLoadMoreRequestKey;
  bool _isBootstrapping = true;
  bool _homeTabActive = true;
  bool _wasBackgrounded = false;

  /// The live conversation is re-read only while Home is on screen; a pendant keeps the app alive in
  /// the background all day.
  ConversationsV3Provider? _v3;
  bool _v3Watching = false;
  Timer? _v3Quick;
  DateTime? _v3QuickSince;
  int? _v3ProcessingSignature;
  String? _v3LiveId;
  DateTime? _v3LiveCreatedAt;
  DateTime? _v3EventRefreshAt;

  // Reliability experiment instant_live_text: while an End hides the live row, the phone's own
  // recogniser is watched, and the first words spoken after that End bring the row back.
  LivePreviewController? _afterEndPreview;
  ({DateTime since, String? captureId})? _afterEnd;

  void _watchSpeechAfterEnd(LivePreviewController? preview, DateTime? since, String? captureId) {
    final watched = since == null ? null : preview;
    _afterEnd = watched == null ? null : (since: since!, captureId: captureId);
    if (identical(_afterEndPreview, watched)) return;
    _afterEndPreview?.removeListener(_onPreviewAfterEnd);
    _afterEndPreview = watched;
    watched?.addListener(_onPreviewAfterEnd);
    // Words may already be there (the End was pressed on another page); never notify during a build.
    if (watched != null) WidgetsBinding.instance.addPostFrameCallback((_) => _onPreviewAfterEnd());
  }

  void _onPreviewAfterEnd() {
    final preview = _afterEndPreview;
    final target = _afterEnd;
    if (!mounted || preview == null || target == null) return;
    final spokenAt = SpeechAfterEnd.firstHeard(preview.lines, target.since);
    if (spokenAt != null) {
      final resumed = context.read<ConversationsV3Provider?>()?.resumeListeningAfterFinish(target.captureId) ?? false;
      if (resumed && ReliabilityExperiments.enabled('vendor_recognizer_on_opened_app')) {
        // Local timing record (no text): how long after the End, and after the first word spoken after
        // it, the live row came back.
        LiveWordsLog.event('listening_row_back', {
          'after_end_ms': DateTime.now().difference(target.since).inMilliseconds,
          'after_first_word_ms': DateTime.now().difference(spokenAt).inMilliseconds,
          'own_results': preview.ownResultsHeard,
          'vendor_words': preview.vendorWordsSeen,
        });
      }
    }
  }

  void _syncV3Watch() {
    final want = mounted && _v3 != null && !_wasBackgrounded && _homeTabActive;
    if (want == _v3Watching) return;
    _v3Watching = want;
    if (want) {
      // Skip ticks while a pushed page (a conversation, settings) covers Home.
      _v3!.watch(
        when: () => mounted && (ModalRoute.of(context)?.isCurrent ?? true),
        // X7: a row that went to transcribing or writing within the last hour re-reads the recent
        // rows on the same 15 s tick. An older stuck row no longer keeps the list re-reading.
        rowsPending: () =>
            mounted &&
            (_v3?.finishRow != null ||
                ConversationsV3Provider.recentlyMidPipeline(
                  context.read<ConversationProvider>().conversations,
                  clock.now(),
                ).isNotEmpty),
        refreshRows: _refreshRecentV3Rows,
      );
    } else {
      _v3?.unwatch();
      _stopV3Quick();
    }
  }

  /// Re-reads the rows that can be changing (created since the earliest recent pending row, the
  /// rows this phone is processing, and [touched]) instead of the whole newest page, and leaves the
  /// scroll position's paging alone.
  Future<void> _refreshRecentV3Rows({Iterable<DateTime> touched = const []}) {
    if (!mounted) return Future.value();
    final provider = context.read<ConversationProvider>();
    final now = clock.now();
    return provider.refreshRecentConversations(ConversationsV3Provider.recentRefreshSince([
      ...touched,
      for (final row in ConversationsV3Provider.recentlyMidPipeline(provider.conversations, now)) row.createdAt,
      for (final row in provider.processingConversations) row.createdAt,
    ], now));
  }

  void _stopV3Quick() {
    _v3Quick?.cancel();
    _v3Quick = null;
    _v3QuickSince = null;
  }

  /// After a frame. Until the server shows the conversation in progress, a streaming capture re-reads
  /// it every 5 s for up to 3 minutes. A capture event (a recording ended or was processed) re-reads
  /// the list and the live conversation instead of adding the recording as a row.
  void _afterV3Frame(
      {required bool waitingForLive,
      required int processingSignature,
      required String? liveId,
      DateTime? liveCreatedAt}) {
    final v3 = _v3;
    if (v3 == null || !mounted) return;
    if (waitingForLive && _v3Watching) {
      final since = _v3QuickSince ??= clock.now();
      if (_v3Quick == null && clock.now().difference(since) < const Duration(minutes: 3)) {
        _v3Quick = Timer.periodic(const Duration(seconds: 5), (_) {
          if (!mounted || clock.now().difference(since) >= const Duration(minutes: 3)) {
            _v3Quick?.cancel();
            _v3Quick = null;
            return;
          }
          // Covered by another page (the live page re-reads for itself): skip, as the 15 s read does.
          if (ModalRoute.of(context)?.isCurrent == false) return;
          unawaited(v3.refresh());
        });
      }
    } else if (!waitingForLive) {
      _stopV3Quick();
    }
    // A capture event changed what is processing (ids, statuses, steps — never object identities, which
    // every list read renews): re-read the list and the live conversation, at most every 10 s.
    final previous = _v3ProcessingSignature;
    _v3ProcessingSignature = processingSignature;
    final last = _v3EventRefreshAt;
    if (previous != null &&
        previous != processingSignature &&
        v3.finishRow == null &&
        (last == null || clock.now().difference(last) >= const Duration(seconds: 10))) {
      _v3EventRefreshAt = clock.now();
      unawaited(v3.refresh());
      unawaited(_refreshRecentV3Rows(touched: [if (liveCreatedAt != null) liveCreatedAt]));
    }
    // The conversation in progress closed (it left the live slot or another took it): re-read the list
    // so it appears as an ordinary row, whatever the processing signature did.
    final previousLive = _v3LiveId;
    final previousLiveCreatedAt = _v3LiveCreatedAt;
    _v3LiveId = liveId;
    _v3LiveCreatedAt = liveCreatedAt;
    if (previousLive != null && previousLive != liveId && v3.finishRow == null) {
      // The closed conversation was created when it opened, possibly hours ago: start there
      // (at most a day back; a longer one is picked up by the next full read).
      unawaited(_refreshRecentV3Rows(touched: [if (previousLiveCreatedAt != null) previousLiveCreatedAt]));
    }
  }

  HomeProvider? _watchedHome;

  void _onHomeProviderChanged() {
    final home = _watchedHome;
    if (home == null) return;
    final active = home.selectedIndex == HomeProvider.homeTab;
    if (active == _homeTabActive) return;
    _homeTabActive = active;
    _syncV3Watch();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final home = context.read<HomeProvider?>();
    if (identical(home, _watchedHome)) return;
    _watchedHome?.removeListener(_onHomeProviderChanged);
    _watchedHome = home;
    _homeTabActive = home == null || home.selectedIndex == HomeProvider.homeTab;
    home?.addListener(_onHomeProviderChanged);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden) {
      _wasBackgrounded = true;
      _syncV3Watch();
    }
    if (state == AppLifecycleState.resumed && _wasBackgrounded) {
      _wasBackgrounded = false;
      _syncV3Watch();
      _scheduleDayRollover();
      if (mounted) setState(() {});
    }
  }

  @override
  bool get wantKeepAlive => true;

  /// Rebuilds Home at local midnight so the live row moves under the new Today.
  LocalDayRollover? _dayTimer;

  void _scheduleDayRollover() {
    _dayTimer?.cancel();
    _dayTimer = LocalDayRollover(() {
      if (mounted) setState(() {});
    });
  }

  PendingWorkStore get _pendingWork => widget.pendingWork ?? PendingWorkStore.instance;

  /// Rebuilds rows whose in-progress state can pass its deadline with nothing else changing.
  Timer? _deadlineTicker;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addObserver(this);
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    _wasBackgrounded = lifecycle == AppLifecycleState.paused || lifecycle == AppLifecycleState.hidden;
    _scheduleDayRollover();
    _deadlineTicker = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted && TickerMode.valuesOf(context).enabled) setState(() {});
    });
    unawaited(_pendingWork.refresh());
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      _v3 = context.read<ConversationsV3Provider?>();
      _syncV3Watch();
      final conversationProvider = context.read<ConversationProvider>();
      try {
        if (widget.requestInitialLoad) {
          await conversationProvider.getInitialConversations(checkDailySummaries: false);
          if (!mounted) return;
          _scheduleDeferred(conversationProvider.checkHasDailySummaries);
        }
      } catch (error, stack) {
        // A failed read is the list's own error state; a throw is unexpected, and still says so.
        Logger.error('Initial Home conversations failed: $error\n$stack');
        if (mounted) {
          OmiFeedback.error(
            context,
            context.l10n.couldNotRefreshConversations,
            actionLabel: context.l10n.tryAgain,
            onAction: () => unawaited(conversationProvider.getInitialConversations()),
          );
        }
      } finally {
        if (mounted) {
          setState(() => _isBootstrapping = false);
          // Keep filesystem scanning off the first navigation/scroll frame.
          _scheduleDeferred(context.read<LocalRecordingsProvider>().refresh);
        }
      }
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
          // A page can come back short (hidden rows) or add nothing new. With the reader still
          // near the end, ask for the next one now instead of waiting for another scroll. Bounded:
          // each page through a hidden run costs hundreds of reads, so one scroll buys a few pages.
          if (mounted && succeeded && _autoLoadMorePages < _maxAutoLoadMorePages) {
            _autoLoadMorePages++;
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) _onScroll(fromScroll: false);
            });
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
    if (_v3Watching) _v3?.unwatch();
    _v3Watching = false;
    _stopV3Quick();
    _deadlineTicker?.cancel();
    _afterEndPreview?.removeListener(_onPreviewAfterEnd);
    _afterEndPreview = null;
    WidgetsBinding.instance.removeObserver(this);
    _watchedHome?.removeListener(_onHomeProviderChanged);
    _watchedHome = null;
    _dayTimer?.cancel();
    for (final timer in _deferred) {
      timer.cancel();
    }
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _onRefresh() async {
    HapticFeedback.mediumImpact();
    final convoProvider = context.read<ConversationProvider>();
    _lastLoadMoreRequestKey = null;
    unawaited(_v3?.refresh());
    unawaited(_pendingWork.refresh());
    Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
    await Future.wait([
      convoProvider.getInitialConversations(),
      Provider.of<LocalRecordingsProvider>(context, listen: false).refresh(),
      // Review's prompt hides when caught up; a pull is how a hidden one comes back.
      if (Provider.of<ReviewProvider?>(context, listen: false) case final review?
          when review.availability != ReviewAvailability.off)
        review.load(),
    ]);
    // The reader pulled; a refresh that failed says so above the rows it kept (§17.4).
    if (mounted && convoProvider.conversationsLoadFailed && convoProvider.conversations.isNotEmpty) {
      OmiFeedback.error(
        context,
        context.l10n.couldNotRefreshConversations,
        actionLabel: context.l10n.tryAgain,
        onAction: () => unawaited(convoProvider.getInitialConversations()),
      );
    }
  }

  /// One day's skeleton. Without [showHeader] it continues a day already headed above it.
  Widget _buildConversationShimmer({bool showHeader = true}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showHeader) ...[
            ShimmerWithTimeout(
              baseColor: OmiColors.surface1,
              highlightColor: OmiColors.surface3,
              child: Container(
                width: 100,
                height: 16,
                decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
              ),
            ),
            const SizedBox(height: 12),
          ],
          // Row-shaped placeholders: the same height and corners as the rows they stand for.
          ...List.generate(
            3,
            (index) => Padding(
              padding: const EdgeInsets.only(bottom: 8.0),
              child: ShimmerWithTimeout(
                baseColor: OmiColors.surface1,
                highlightColor: OmiColors.surface3,
                child: Container(
                  height: 72,
                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingShimmer() {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) => _buildConversationShimmer(showHeader: true),
        childCount: 3,
      ),
    );
  }

  Widget _buildLoadMoreShimmer() {
    return Padding(
      padding: const EdgeInsets.only(top: 8.0),
      child: ShimmerWithTimeout(
        baseColor: OmiColors.surface1,
        highlightColor: OmiColors.surface3,
        child: Container(
          height: 72,
          margin: const EdgeInsets.symmetric(horizontal: 16.0),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
        ),
      ),
    );
  }

  /// Every row kind on Home, drawn by exactly one widget.
  Widget _rowWidget(HomeRow row, DateTime date) => switch (row) {
        HomeLiveRow() => HomeLiveRowView(key: const ValueKey('home_live'), row: row),
        HomeFinishingRow() => HomeFinishingRowView(key: const ValueKey('home_finishing'), row: row),
        HomeConversationRow(:final conversation, :final index) => ConversationListItem(
            key: ValueKey(conversation.id),
            conversation: conversation,
            conversationIdx: index,
            date: date,
          ),
        HomeSavedRow(:final recording) => RecordingListItem(key: ValueKey('rec_${recording.id}'), recording: recording),
        HomeLockedRow() => HomeLockedRowView(key: ValueKey(row.key), row: row),
      };

  @override
  Widget build(BuildContext context) {
    super.build(context);
    // The page shell rebuilds only for its own state; list changes rebuild the list below it.
    return Selector2<ConversationProvider, LocalRecordingsProvider, _HomeSnapshot>(
      selector: (_, conversations, recordings) => _homeSnapshot(conversations, recordings),
      builder: (context, _, __) => _buildHome(context),
    );
  }

  Widget _buildHome(BuildContext context) {
    final convoProvider = context.read<ConversationProvider>();
    final recordings = context.read<LocalRecordingsProvider>();
    final v3 = context.watch<ConversationsV3Provider?>();
    // Only what decides rows: the live row's own content listens for itself, so a capture tick does
    // not rebuild the whole list.
    final (streaming, captureId, transcribeLater, livePreview) =
        context.select<CaptureProvider, (bool, String?, bool, LivePreviewController?)>((c) => (
              EpisodePresentation.streamingSource(c) != null,
              c.activeRecordingId,
              c.isPhoneMicBatchRecording || (SharedPreferencesUtil().batchModeEnabled && c.havingRecordingDevice),
              c.livePreview,
            ));
    // Under vendor_recognizer_on_opened_app the watched lines are the merged ones: the phone's own
    // recogniser's, and the vendor's where it returned nothing.
    if (ReliabilityExperiments.enabled('instant_live_text') ||
        ReliabilityExperiments.enabled('vendor_recognizer_on_opened_app')) {
      _watchSpeechAfterEnd(livePreview, v3?.listeningSuppressedSince(captureId), captureId);
    }

    // Home's own view: no search, filter or selection. Showing short or discarded conversations widens the
    // list; it is not a filter, so the live row and saved recordings stay.
    final defaultView = convoProvider.showsPendingFinishOnHome;
    final live = v3?.live;
    final liveRemoved = live != null &&
        (live.discarded ||
            convoProvider.memoriesToDelete.containsKey(live.id) ||
            SharedPreferencesUtil().isConversationDeleteConfirmed(live.id));

    // The finish row after End, until the server's own row for it is listed or it settles.
    final manualFinish = v3?.finishRow;
    if (v3 != null && v3.takeHomeReconcile()) {
      // An accepted finish reached its deadline: read the list once, wherever the reader is.
      WidgetsBinding.instance.addPostFrameCallback(
          (_) => unawaited(convoProvider.forceRefreshConversations().then<void>((_) {}, onError: (Object _) {})));
    }
    final listedNow = convoProvider.groupedConversations.values.expand((rows) => rows).toList();
    // Conversations this phone knows are processing but the list has not caught up with yet (and every
    // processing row a legacy-shaped server answer keeps out of the list). The model drops duplicates.
    final processing = defaultView
        ? convoProvider.processingConversations.where((c) => c.id != OptimisticProcessingPlaceholder.id)
        : const <ServerConversation>[];
    final terminalFinish = manualFinish == null ? null : v3!.finishTerminalMatch(convoProvider.conversations);
    final finishHandedOff = manualFinish != null && v3!.finishHasSuccessor(listedNow.where(listedOnHome));
    final finishSettled = finishHandedOff || terminalFinish != null;
    final showFinish = defaultView && manualFinish != null && !finishSettled;
    if (manualFinish != null && finishSettled) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) v3!.acknowledgeManualFinish(manualFinish);
      });
    }

    final callActive = context.select<PhoneCallProvider?, bool>((p) => switch (p?.callState) {
          PhoneCallState.active || PhoneCallState.connecting || PhoneCallState.ringing => true,
          _ => false,
        });
    final usage = context.watch<UsageProvider?>()?.subscription;
    final held =
        defaultView ? lockedHeldRecordings(usage?.heldAudio, usage?.processingBacklog) : const <HeldAudioRecording>[];
    final heldMore = (usage?.heldAudio?.count ?? 0) - held.length;

    final now = clock.now();
    final model = buildHome(HomeInputs(
      now: now,
      listed: [...listedNow, ...processing],
      defaultView: defaultView,
      live: liveRemoved ? null : live,
      // The owner deleted the conversation in progress: nothing stands in for it.
      streaming: streaming && !liveRemoved,
      callActive: callActive,
      transcribeLater: transcribeLater,
      listeningSuppressed: v3?.suppressListeningAfterFinish(captureId) ?? false,
      finishing: showFinish ? manualFinish : null,
      saved: recordings.recordings,
      held: held,
      heldMore: heldMore > 0 ? heldMore : 0,
      hiddenIds: convoProvider.memoriesToDelete.keys.toSet(),
    ));

    // Polling: until the server shows the capture as a conversation, re-read it quickly.
    final processingSignature =
        Object.hashAll(convoProvider.processingConversations.map((c) => Object.hash(c.id, c.status, c.homeStep)));
    WidgetsBinding.instance.addPostFrameCallback((_) => _afterV3Frame(
          waitingForLive: streaming && live == null,
          processingSignature: processingSignature,
          liveId: live?.id,
          liveCreatedAt: live?.createdAt,
        ));

    final apiPhase = convoProvider.apiViewState.phase;
    final showTypedStatus = apiPhase == ApiViewPhase.error ||
        apiPhase == ApiViewPhase.locked ||
        apiPhase == ApiViewPhase.terminal ||
        apiPhase == ApiViewPhase.authenticationRequired ||
        apiPhase == ApiViewPhase.empty;
    final loading = convoProvider.isLoadingConversations ||
        convoProvider.isFetchingConversations ||
        convoProvider.isAwaitingInitialFetchRetry;
    final hasListRows = model.rows.any((r) => r is! HomeLiveRow && r is! HomeFinishingRow);

    if (defaultView) HomeRowsHealth.note(model.rows.length);

    // Flatten the model into list items: a header per day, then its rows.
    final items = <Widget>[];
    for (final (dayIndex, day) in model.days.indexed) {
      final isFirst = dayIndex == 0;
      final isToday = day.date == homeDay(now);
      items.add(defaultView && !isToday
          ? DaySummaryHeader(
              key: ValueKey('date_${day.date.toIso8601String()}'),
              date: day.date,
              isFirst: isFirst,
              open: widget.openDaySummary,
            )
          : DateListItem(key: ValueKey('date_${day.date.toIso8601String()}'), date: day.date, isFirst: isFirst));
      for (final row in day.rows) {
        items.add(_rowWidget(row, day.date));
      }
      items.add(const SizedBox(height: 10));
    }

    final Widget body;
    if (_isBootstrapping && !hasListRows) {
      body = _buildLoadingShimmer();
    } else if (!hasListRows &&
        showTypedStatus &&
        apiPhase != ApiViewPhase.empty &&
        !convoProvider.hasActiveHomeFilter) {
      body = SliverFillRemaining(
        hasScrollBody: false,
        child: Center(child: ConversationApiStatus(provider: convoProvider)),
      );
    } else if (!hasListRows && loading) {
      body = _buildLoadingShimmer();
    } else if (!hasListRows && !model.isEmpty) {
      // Only the live row (or Finishing…): it opens Today on its own, with no hero under it.
      body = const SliverToBoxAdapter(child: SizedBox.shrink());
    } else if (!hasListRows && !convoProvider.hasActiveHomeFilter && defaultView) {
      // Friendly hero for brand-new users with zero conversations.
      body = SliverFillRemaining(
        hasScrollBody: false,
        child: Center(
          child: NoConversationsHero(
            // The typed-state key the conversation surface contract reads for a successful empty list.
            key: apiPhase == ApiViewPhase.empty ? const ValueKey('omi.conversations.empty') : null,
            message: switch (convoProvider.homeEmptyExplanation) {
              HomeEmptyExplanation.tooShort => context.l10n.tooShortDesc,
              HomeEmptyExplanation.discardedOnly => context.l10n.discardedOnlyRecording,
              HomeEmptyExplanation.none => null,
            },
          ),
        ),
      );
    } else if (!hasListRows) {
      body = SliverToBoxAdapter(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.only(top: 32.0),
            child: EmptyConversationsWidget(
              isStarredFilterActive: convoProvider.showStarredOnly,
              dateFilterLabel: convoProvider.selectedStartDate == null
                  ? null
                  : _conversationDateRangeLabel(
                      context, convoProvider.selectedStartDate!, convoProvider.selectedEndDate),
            ),
          ),
        ),
      );
    } else {
      body = SliverList(
        delegate: SliverChildBuilderDelegate(childCount: items.length + 1, (context, index) {
          if (index < items.length) return items[index];
          if (convoProvider.isLoadingConversations) return _buildLoadMoreShimmer();
          // A failed older page ends the list with one quiet line, not silence (X6); scrolling does
          // not retry it on its own.
          if (convoProvider.loadMoreFailed) {
            return OmiLoadMoreFailed(
              key: const Key('conversations_load_more_failed'),
              onRetry: () async {
                _lastLoadMoreRequestKey = null;
                final provider = context.read<ConversationProvider>();
                if (provider.hasMoreConversations) await provider.getMoreConversationsFromServer();
              },
            );
          }
          return VisibilityDetector(
            key: const Key('conversations-key'),
            onVisibilityChanged: (info) {
              if (info.visibleFraction > 0) _requestMoreIfNeeded(context.read<ConversationProvider>());
            },
            child: const SizedBox(height: 20, width: double.maxFinite),
          );
        }),
      );
    }

    // Rows ink on the page itself, so Home draws correctly wherever it is mounted.
    return Material(
      type: MaterialType.transparency,
      child: RefreshIndicator(
        onRefresh: _onRefresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: CustomScrollView(
          controller: _scrollController,
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // At most one prompt: payment, then device, then voice profile, then Review.
            if (defaultView) const SliverToBoxAdapter(child: HomePromptSlot()),
            // A live capture (or a finish) with nothing else listed yet still opens Today.
            if (!hasListRows && model.days.isNotEmpty) SliverList(delegate: SliverChildListDelegate([...items])),
            if (hasListRows && showTypedStatus && apiPhase != ApiViewPhase.empty)
              SliverToBoxAdapter(child: ConversationApiStatus(provider: convoProvider)),
            body,
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
      ),
    );
  }
}
