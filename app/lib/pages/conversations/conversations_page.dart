import 'package:clock/clock.dart';
import 'package:omi/utils/local_day_rollover.dart';
// The conversations list page: paged list with filter-keyed load-more state,
// plus the capture-status surfaces stacked above it (processing card, held
// audio, on-device queue banners).
//
// The page stays alive across tab switches (AutomaticKeepAliveClientMixin), so
// scroll position and pagination survive background sync mutations; load-more
// state is keyed by the active filter and resets deliberately on filter change.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/v3_live_placeholder_row.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'live_episode_visibility.dart';
import 'home_rows.dart';
import 'home_card_rows.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'home_rows_health.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:omi/pages/conversations/background_conversations.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps_setting.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/home/widgets/payment_issue_row.dart';
import 'package:omi/pages/home/widgets/quiet_payer_row.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'package:omi/widgets/home_bottom_bar.dart';

part 'conversations_processing_rows.dart';

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
  liveEpisode,
  v3LivePlaceholder,
  processing,
  conversation,
  recording,
  heldRecording,
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
  HomeEmptyExplanation homeEmptyExplanation,
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
    homeEmptyExplanation: conversations.homeEmptyExplanation,
  );
}

List<_ConversationListRow> _buildConversationListRows({
  required List<DateTime> dates,
  required Map<DateTime, List<ServerConversation>> conversationsByDate,
  required Map<DateTime, List<LocalRecording>> recordingsByDate,
  // Locked rows keep their index in the server's list, which the builder reads back.
  Map<DateTime, List<int>> heldByDate = const {},
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
    final held = heldByDate[date] ?? const <int>[];
    if (entries.isEmpty && held.isEmpty) continue;

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

    for (final index in held) {
      rows.add((
        kind: _ConversationListRowKind.heldRecording,
        date: date,
        isFirst: false,
        conversation: null,
        recording: null,
        conversationIndex: index,
      ));
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

/// [rows] with conversation [id] moved to the top of its day, right under the day's header: the
/// conversation in progress leads its day even when a later call or import started after it.
List<_ConversationListRow> _pinFirstInDay(List<_ConversationListRow> rows, String id) {
  final at = rows.indexWhere((r) => r.kind == _ConversationListRowKind.conversation && r.conversation?.id == id);
  if (at < 0) return rows;
  final row = rows[at];
  final header = rows.lastIndexWhere((r) => r.kind == _ConversationListRowKind.dateHeader && r.date == row.date, at);
  if (header < 0 || header == at - 1) return rows;
  return [
    ...rows.take(header + 1),
    row,
    for (var i = header + 1; i < rows.length; i++)
      if (i != at) rows[i]
  ];
}

/// [rows] with the live episode right under today's header. With no today in the list,
/// the episode opens Today itself, carrying its own header.
/// [byDate] without the conversations Home leaves to the daily recap (background notes,
/// David 2026-10-23). Days left empty drop out when the rows are built.
Map<DateTime, List<ServerConversation>> _withoutBackground(Map<DateTime, List<ServerConversation>> byDate) => {
      for (final entry in byDate.entries)
        entry.key: [
          for (final c in entry.value)
            if (!leftToDailyRecap(c)) c,
        ],
    };

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

/// Home: the live capture row, the Daily Recaps row (when on), then every conversation, newest first, loading
/// more as it scrolls. Search, folders, starred and places live in the search overlay the header's
/// search button opens, so this list is never filtered in place.
class ConversationsPage extends StatefulWidget {
  const ConversationsPage(
      {super.key, this.requestInitialLoad = true, this.loadRecaps, this.pendingWork, this.openDaySummary});

  /// Production stays true. Widget tests that already call
  /// [ConversationProvider.getInitialConversations] inside `runAsync` pass
  /// false so initState does not queue loopback I/O on the fake-async clock.
  final bool requestInitialLoad;

  /// Injectable for tests and the visual audit; defaults to the recaps endpoint.
  final RecentRecapsLoader? loadRecaps;

  /// Test seam for a v3 day header's tap.
  final DaySummaryOpener? openDaySummary;

  /// Injectable for tests; defaults to [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  @override
  State<ConversationsPage> createState() => _ConversationsPageState();
}

class _ConversationsPageState extends State<ConversationsPage>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  TextEditingController textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  HomeFeedProvider? _feed;
  bool _usesCards(ConversationProvider p) =>
      _feed != null &&
      context.read<ConversationsV3Provider?>()?.suppressesLegacy != true &&
      !_feed!.unsupported &&
      !p.hasActiveSearch &&
      !p.hasActiveHomeFilter &&
      !p.showShortConversations &&
      !p.showDiscardedConversations;

  /// Follow-up pages asked for without a new scroll since the reader last moved; see
  /// [_requestMoreIfNeeded].
  int _autoLoadMorePages = 0;
  static const _maxAutoLoadMorePages = 4;

  void _prefetchCards({bool fromScroll = true}) {
    if (!_scrollController.hasClients) return;
    if (fromScroll) _autoLoadMorePages = 0;
    final source = context.read<ConversationProvider>();
    _feed?.continuePreparation();
    if (!_usesCards(source)) {
      if (_scrollController.position.extentAfter < _scrollController.position.viewportDimension * 2) {
        _requestMoreIfNeeded(source);
      }
      return;
    }
    final position = _scrollController.position;
    if (position.extentAfter < position.viewportDimension * 2 && _feed!.problem == null) unawaited(_feed!.loadMore());
  }

  final GlobalKey<HomeDailyRecapsState> _recapsKey = GlobalKey<HomeDailyRecapsState>();
  String? _loadMoreFilterKey;
  String? _lastLoadMoreRequestKey;
  bool _isBootstrapping = true;
  bool _initialOverlayPending = false;
  Completer<void>? _initialOverlayReady;
  ({String owner, HomeEpisodeLayout layout})? _fallbackHomeLayout;
  final Set<String> _paintedStandaloneIds = {};
  bool _homeTabActive = true;
  bool _wasBackgrounded = false;

  /// v3: the live conversation is re-read only while Home is on screen; a pendant keeps the app
  /// alive in the background all day.
  ConversationsV3Provider? _v3;
  bool _v3Watching = false;
  Timer? _v3Quick;
  DateTime? _v3QuickSince;
  int? _v3ProcessingSignature;
  String? _v3LiveId;
  DateTime? _v3LiveCreatedAt;
  DateTime? _v3EventRefreshAt;

  /// Episodes were asked for before the switch answered (and so made no call); ask again once it says
  /// this account is not on v3.
  bool _legacyAfterAnswer = false;

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

  /// v3 Home after a frame. Until the server shows the conversation in progress, a streaming capture
  /// re-reads it every 5 s for up to 3 minutes. A capture event (a recording ended or was processed)
  /// re-reads the list and the live conversation instead of adding the recording as a row.
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

  /// The switch answered "not v3" after Home started: start the episode reads it held back.
  void _afterLegacyAnswer() {
    if (!_legacyAfterAnswer || !mounted) return;
    final v3 = _v3;
    if (v3 == null || !v3.resolved || v3.v3) return;
    _legacyAfterAnswer = false;
    final episodes = context.read<EpisodeProvider?>();
    if (episodes != null) unawaited(episodes.refreshLive());
  }

  HomeProvider? _watchedHome;

  void _releaseHomeLayout() {
    _fallbackHomeLayout = null;
    _paintedStandaloneIds.clear();
  }

  void _onHomeProviderChanged() {
    final home = _watchedHome;
    if (home == null) return;
    final active = home.selectedIndex == HomeProvider.homeTab;
    if (active == _homeTabActive) return;
    _homeTabActive = active;
    _syncV3Watch();
    final source = context.read<ConversationProvider>();
    _feed?.setActive(active &&
        !_wasBackgrounded &&
        !source.hasActiveSearch &&
        !source.hasActiveHomeFilter &&
        !source.showShortConversations &&
        !source.showDiscardedConversations);
    if (active && _feed?.preparationReady == true) unawaited(_feed!.refresh());
    // Re-entering Home releases an outage-era grouping.
    // Skip the rebuild when there is nothing to update (tab_switch perf budget).
    if (active && mounted && (_fallbackHomeLayout != null || _paintedStandaloneIds.isNotEmpty)) {
      setState(_releaseHomeLayout);
    }
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
      _feed?.setActive(false);
      _syncV3Watch();
    }
    if (state == AppLifecycleState.resumed && _wasBackgrounded) {
      _wasBackgrounded = false;
      _syncV3Watch();
      final source = context.read<ConversationProvider>();
      _feed?.setActive(_homeTabActive &&
          !source.hasActiveSearch &&
          !source.hasActiveHomeFilter &&
          !source.showShortConversations &&
          !source.showDiscardedConversations);
      _scheduleDayRollover();
      if (mounted) setState(_releaseHomeLayout);
    }
  }

  @override
  bool get wantKeepAlive => true;

  /// Rebuilds Home at local midnight so the pending row moves under the new Today.
  LocalDayRollover? _dayTimer;

  void _scheduleDayRollover() {
    _dayTimer?.cancel();
    _dayTimer = LocalDayRollover(() {
      if (mounted) setState(() {});
    });
  }

  PendingWorkStore get _pendingWork => widget.pendingWork ?? PendingWorkStore.instance;

  void _onPendingWorkChanged() {
    if (mounted) setState(() {});
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_prefetchCards);
    WidgetsBinding.instance.addObserver(this);
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    _wasBackgrounded = lifecycle == AppLifecycleState.paused || lifecycle == AppLifecycleState.hidden;
    HomeDailyRecapsSetting.reload();
    _scheduleDayRollover();
    _pendingWork.addListener(_onPendingWorkChanged);
    unawaited(_pendingWork.refresh());
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      _v3 = context.read<ConversationsV3Provider?>();
      _syncV3Watch();
      // First launch after this build: learn which Home this account has before any episode or feed
      // read (a v3 account makes none). Later launches know it from the remembered answer.
      if (_v3 case final v3? when !v3.resolved) {
        await v3.refresh().timeout(const Duration(seconds: 3), onTimeout: () {});
        if (!mounted) return;
        if (!v3.resolved) _legacyAfterAnswer = true;
      }
      // The episodes capability (and any live episode) decides how the live capture reads on Home.
      final episodes = context.read<EpisodeProvider?>();
      if (episodes != null) unawaited(episodes.refreshLive());
      final conversationProvider = context.read<ConversationProvider>();
      episodes?.observeHomeConversations(conversationProvider);
      _feed = context.read<HomeFeedProvider?>();
      _feed?.setActive(!_wasBackgrounded && _homeTabActive);
      if (widget.requestInitialLoad && _feed != null && _usesCards(conversationProvider)) {
        await _feed!.start();
        if (!mounted) return;
        if (!_feed!.unsupported) {
          setState(() => _isBootstrapping = false);
          _scheduleDeferred(context.read<LocalRecordingsProvider>().refresh);
          return;
        }
      }
      final today = DateUtils.dateOnly(clock.now());
      final initialFrom = conversationProvider.groupedConversations.keys.fold<DateTime>(
        today.subtract(const Duration(days: 7)),
        (oldest, day) => day.isBefore(oldest) ? day : oldest,
      );
      _initialOverlayPending = widget.requestInitialLoad && episodes != null;
      Future<bool> loadOverlay(DateTime from) =>
          episodes!.refreshHome(from, today.add(const Duration(days: 1)), bootstrap: true).onError((error, stack) {
            Logger.error('Initial Home overlay failed: $error');
            return false;
          });
      var overlay = _initialOverlayPending ? loadOverlay(initialFrom) : Future.value(true);
      var overlayFrom = initialFrom;
      try {
        if (widget.requestInitialLoad) {
          await conversationProvider.getInitialConversations(checkDailySummaries: false);
          if (!mounted) return;
          _scheduleDeferred(conversationProvider.checkHasDailySummaries);
          // The first page may reach beyond seven days. Cover its actual range
          // under the same single deadline, rather than exposing older members.
          final days = conversationProvider.groupedConversations.keys;
          final oldest = days.isEmpty ? today : days.reduce((a, b) => a.isBefore(b) ? a : b);
          if (episodes != null && oldest.isBefore(initialFrom)) {
            overlayFrom = oldest;
            overlay = loadOverlay(oldest);
          }
          final settled = _settleInitialOverlay(overlay, () => loadOverlay(overlayFrom));
          unawaited(
            settled.whenComplete(() {
              if (mounted) setState(() => _initialOverlayPending = false);
            }),
          );
          await settled.timeout(const Duration(milliseconds: 500), onTimeout: () {});
        }
      } catch (error, stack) {
        Logger.error('Initial Home conversations failed: $error\n$stack');
        _initialOverlayPending = false;
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

  /// Retry failed history before publishing source rows; persistent failure keeps
  /// the last cached projection after a short deadline. All timers leave with Home.
  Future<void> _settleInitialOverlay(Future<bool> first, Future<bool> Function() retry) {
    final ready = _initialOverlayReady = Completer<void>();
    Timer? deadline;
    void finish() {
      if (ready.isCompleted) return;
      deadline?.cancel();
      _deferred.remove(deadline);
      ready.complete();
    }

    Future<void> attempt(Future<bool> read, int retries) async {
      final complete = await read;
      if (ready.isCompleted || !mounted) return;
      if (complete) {
        finish();
      } else {
        if (deadline == null) {
          deadline = Timer(const Duration(seconds: 2), () {
            if (ready.isCompleted || !mounted) return;
            // A retry may still publish after this deadline. Pin only layout so
            // that result cannot regroup rows the reader has already seen.
            _fallbackHomeLayout = (
              owner: SharedPreferencesUtil().uid,
              layout: HomeEpisodeLayout(context.read<EpisodeProvider?>()?.homeEpisodes ?? const []),
            );
            finish();
          });
          _deferred.add(deadline!);
        }
        if (retries > 0) {
          _scheduleDeferred(() => attempt(retry(), retries - 1));
        }
      }
    }

    unawaited(attempt(first, 2));
    return ready.future;
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
              if (mounted) _prefetchCards(fromScroll: false);
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
    WidgetsBinding.instance.removeObserver(this);
    _watchedHome?.removeListener(_onHomeProviderChanged);
    _watchedHome = null;
    _pendingWork.removeListener(_onPendingWorkChanged);
    _dayTimer?.cancel();
    if (_initialOverlayReady != null && !_initialOverlayReady!.isCompleted) {
      _initialOverlayReady!.complete();
    }
    _initialOverlayReady = null;
    for (final timer in _deferred) {
      timer.cancel();
    }
    _scrollController.dispose();
    super.dispose();
  }

  /// One day's skeleton. Without [showHeader] it continues a day already headed above it.
  Widget _buildConversationShimmer({bool showHeader = true}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showHeader) ...[
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
          ],
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

  Widget _buildLoadingShimmer() {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) => _buildConversationShimmer(showHeader: true),
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
    // Episodes on: a streaming capture is the live episode's row in Today, not a card above the recaps.
    final episodes = context.watch<EpisodeProvider?>();
    final episodesOn = episodes?.enabled == true;
    final streaming = context.select<CaptureProvider, bool>((c) => EpisodePresentation.streamingSource(c) != null);
    final captureId = context.select<CaptureProvider, String?>((c) => c.activeRecordingId);
    final episodeLive = episodesOn && streaming;
    final filling = episodesOn ? fillingSeconds(_pendingWork.pending) : const <String, int>{};
    // Recordings and conversations (v3): a flat list of conversations, the one in progress on top.
    final v3 = context.watch<ConversationsV3Provider?>();
    final v3On = v3?.v3 == true;
    // No answer yet (first launch): the plain list, with no feed or episode reads.
    final v3Pending = v3 != null && !v3.resolved;
    if (_legacyAfterAnswer) WidgetsBinding.instance.addPostFrameCallback((_) => _afterLegacyAnswer());
    return Selector2<ConversationProvider, LocalRecordingsProvider, _ConversationPageSnapshot>(
      selector: (_, conversationProvider, recordingsProvider) =>
          _conversationPageSnapshot(conversationProvider, recordingsProvider),
      builder: (context, snapshot, child) {
        final convoProvider = context.read<ConversationProvider>();
        final feed = context.watch<HomeFeedProvider?>();
        final cardsOn = feed != null &&
            !v3On &&
            !v3Pending &&
            !feed.unsupported &&
            !convoProvider.hasActiveSearch &&
            !convoProvider.hasActiveHomeFilter &&
            !convoProvider.showShortConversations &&
            !convoProvider.showDiscardedConversations;
        if (feed != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            feed.setActive(!_wasBackgrounded &&
                _homeTabActive &&
                !convoProvider.hasActiveSearch &&
                !convoProvider.hasActiveHomeFilter &&
                !convoProvider.showShortConversations &&
                !convoProvider.showDiscardedConversations);
            if (feed.preparationReady &&
                feed.unsupported &&
                (!_scrollController.hasClients || _scrollController.offset <= 20)) {
              unawaited(feed.refresh());
            }
            if (cardsOn && widget.requestInitialLoad && !feed.initialized) unawaited(feed.start());
          });
        }
        final defaultHome = convoProvider.showsDefaultHome;
        final hiddenByLive =
            episodeLive && defaultHome ? hiddenLiveConversations(episodes!.liveConversationIds) : const <String>{};
        final v3Home = v3On && defaultHome;
        final activityOnlyFailures = v3On || _pendingWork.homeProcessingToday;
        final v3Live = v3Home ? v3!.live : null;
        final manualFinish = v3On ? v3!.finishRow : null;
        if (v3On && v3!.takeHomeReconcile()) {
          // An accepted finish reached its deadline: read the list once, wherever the reader is.
          WidgetsBinding.instance.addPostFrameCallback(
              (_) => unawaited(convoProvider.forceRefreshConversations().then<void>((_) {}, onError: (Object _) {})));
        }
        final terminalFinish = manualFinish == null ? null : v3!.finishTerminalMatch(convoProvider.conversations);
        final finishHandedOff = v3Home &&
            manualFinish != null &&
            v3!.finishHasSuccessor(
                convoProvider.groupedConversations.values.expand((rows) => rows).where(shownOnV3Home));
        final finishSettled = finishHandedOff || terminalFinish != null;
        final showManualFinish = v3Home && manualFinish != null && !finishSettled;
        if (manualFinish != null && finishSettled) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) v3!.acknowledgeManualFinish(manualFinish);
          });
        }
        // A streaming capture with no server window to show (none yet, between windows, or one Home
        // hides) is the live placeholder row: first under Today, the slot the server's live row takes
        // when it arrives, so the row never jumps sections. An Omi call is shown as the call card
        // instead; the placeholder never doubles it.
        final callActive = context.select<PhoneCallProvider?, bool>((p) => switch (p?.callState) {
              PhoneCallState.active || PhoneCallState.connecting || PhoneCallState.ringing => true,
              _ => false,
            });
        final v3LiveShown = v3Live != null &&
            v3Live.v3?.homeHidden != true &&
            !isFailedConversation(v3Live) &&
            !v3Live.discarded &&
            !convoProvider.memoriesToDelete.containsKey(v3Live.id) &&
            !SharedPreferencesUtil().isConversationDeleteConfirmed(v3Live.id);
        // A deleted or discarded live window shows nothing (the owner removed it); only a window Home
        // hides (still below the word minimum, say) is stood in for by the placeholder.
        final liveRemoved = v3Live != null &&
            (v3Live.discarded ||
                convoProvider.memoriesToDelete.containsKey(v3Live.id) ||
                SharedPreferencesUtil().isConversationDeleteConfirmed(
                  v3Live.id,
                ));
        final livePlaceholder = v3Home &&
            streaming &&
            !v3!.suppressListeningAfterFinish(captureId) &&
            (v3Live == null || v3Live.v3?.homeHidden == true) &&
            !liveRemoved &&
            !callActive;
        if (v3Home) {
          final waiting = streaming && v3Live == null;
          final signature =
              Object.hashAll(snapshot.processingConversations.map((c) => Object.hash(c.id, c.status, c.homeStep)));
          WidgetsBinding.instance.addPostFrameCallback((_) => _afterV3Frame(
                waitingForLive: waiting,
                processingSignature: signature,
                liveId: v3Live?.id,
                liveCreatedAt: v3Live?.createdAt,
              ));
        }
        // Unsynced local recordings (batch/offline mode) shown inline with conversations,
        // grouped into the same date buckets. Only in the default view (no search/folder/
        // starred/daily-summaries filter).
        final bool showRecordings =
            !convoProvider.hasActiveSearch && convoProvider.selectedFolderId == null && !convoProvider.showStarredOnly;
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
        // v3: a conversation's tile shows its processing; capture-side processing rows are recordings.
        final bool hasProcessingConversations = showManualFinish ||
            (!v3Home && snapshot.processingConversations.any((c) => !activityOnlyFailures || !isFailedConversation(c)));
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
        var conversationsByDate = hiddenByLive.isEmpty
            ? convoProvider.groupedConversations
            : {
                for (final entry in convoProvider.groupedConversations.entries)
                  entry.key: [
                    for (final c in entry.value)
                      if (!hiddenByLive.contains(c.id)) c,
                  ],
              };
        if (!defaultHome && activityOnlyFailures) {
          final today = localHomeDay(clock.now());
          conversationsByDate = {
            for (final entry in conversationsByDate.entries)
              entry.key: [
                for (final c in entry.value)
                  if (!isFailedConversation(c) &&
                      (!_pendingWork.homeProcessingToday ||
                          !showRecordings ||
                          convoProvider.isSelectionModeActive ||
                          localHomeDay(c.startedAt ?? c.createdAt) == today ||
                          !{HomeStep.transcribing, HomeStep.writingNotes}.contains(homeStepOf(c))))
                    c,
              ],
          };
        }
        if (v3Home) {
          // The server lists Home-visible conversations; the in-progress one comes from the live read
          // and leads its day.
          conversationsByDate = {
            for (final entry in conversationsByDate.entries)
              entry.key: [
                for (final c in entry.value)
                  if (c.id != v3Live?.id && shownOnV3Home(c)) c,
              ],
          };
          if (v3LiveShown) {
            // The conversation in progress always leads Today, even when it started before midnight:
            // the live row never sits in an earlier day or above the day list (David, 2026-11-21).
            final day = localHomeDay(clock.now());
            conversationsByDate[day] = [v3Live, ...?conversationsByDate[day]];
          }
        }
        final cardById = <String, HomeFeedCard>{};
        final unknownCardDay = DateTime(1);
        if (cardsOn) {
          conversationsByDate = {};
          final hidden = {...convoProvider.memoriesToDelete.keys, ...hiddenByLive};
          for (final card in feed.items) {
            if (card.kind == 'conversation' &&
                (convoProvider.memoriesToDelete.containsKey(card.detailId) ||
                    (hidden.contains(card.detailId) && card.homeStep != 'ready'))) {
              continue;
            }
            if (card.kind == 'episode' && episodeLive && card.detailId == episodes?.live?.id) continue;
            final seed = card.displaySeed();
            cardById[seed.id] = card;
            (conversationsByDate[card.startedAt == null ? unknownCardDay : localHomeDay(card.startedAt!)] ??= [])
                .add(seed);
          }
          convoProvider.setHomeCardSelectionSeeds([
            for (final card in feed.items)
              if (card.kind == 'conversation') card.displaySeed(),
          ]);
        }
        final projectedEpisodes = <String, HomeRow>{};
        final projectedMemberIds = <String>{...hiddenByLive};
        final projectedProcessingIds = <String>{};
        if (defaultHome && !cardsOn && !v3Home) {
          final today = clock.now();
          final days = conversationsByDate.keys;
          final from = days.isEmpty
              ? DateTime(today.year, today.month, today.day - 7)
              : days.reduce((a, b) => a.isBefore(b) ? a : b);
          final to = DateTime(today.year, today.month, today.day + 1);
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted && episodesOn && !_isBootstrapping && !_initialOverlayPending) {
              unawaited(episodes!.refreshHome(from, to));
            }
          });
          final latestEpisodes = episodes?.homeEpisodes ?? const [];
          final heldLayout = _fallbackHomeLayout;
          final holdingLayout = heldLayout != null && heldLayout.owner == SharedPreferencesUtil().uid;
          final paintEpisodes = holdingLayout
              ? heldLayout.layout.apply(latestEpisodes, standaloneIds: _paintedStandaloneIds)
              : latestEpisodes;
          // Home and live snapshots can disagree about the latest membership.
          // The same live episode owns its closed members in both insertion paths.
          for (final episode in paintEpisodes) {
            if (episode.live &&
                (episodeLive && episode.id == episodes?.live?.id ||
                    episode.conversationIds.any(hiddenByLive.contains))) {
              projectedMemberIds.addAll(episode.conversationIds);
            }
          }
          final listed = [for (final list in conversationsByDate.values) ...list];
          final listedIds = {for (final c in listed) c.id};
          final projected = buildHomeRows(
            // Just-ended rows fold into the same Processing run as everything else unfinished.
            [
              ...listed,
              for (final c in snapshot.processingConversations)
                if (!listedIds.contains(c.id) && !hiddenByLive.contains(c.id)) c,
            ],
            paintEpisodes,
            enabled: episodesOn,
            groupAwaitingTranscript: true,
            now: clock.now(),
            processingTodayOnly: _pendingWork.homeProcessingToday,
            singleProcessingRow: true,
            neutralUnknownSteps: true,
            processingDay: localHomeDay(clock.now()),
            activityOnlyFailures: activityOnlyFailures,
            processingTitle: context.l10n.wrappedProcessingDefault,
            finishingTitle: context.l10n.episodeFinishingUp,
            liveConversationIds: hiddenByLive,
            liveEpisodeId: episodeLive ? episodes?.live?.id : null,
            deletedIds: {...convoProvider.memoriesToDelete.keys, ...(episodes?.hiddenHomeMembers ?? const <String>{})},
            knownConversations: snapshot.conversations,
            processingConversations: snapshot.processingConversations,
          );
          conversationsByDate = {};
          for (final row in projected) {
            (conversationsByDate[row.day] ??= []).add(row.conversation);
            projectedMemberIds.addAll(row.episodeConversationIds);
            if (row.isProcessing) projectedProcessingIds.add(row.conversation.id);
            if (row.episode != null) projectedEpisodes[row.conversation.id] = row;
            if (holdingLayout && !_isBootstrapping && !_initialOverlayPending) {
              if (row.episode == null) {
                _paintedStandaloneIds.add(row.conversation.id);
              } else if (row.episode!.id.isEmpty) {
                // An unassigned Processing run is also an already-painted row.
                _paintedStandaloneIds.addAll(row.episodeConversationIds);
              }
            }
          }
          if (holdingLayout && !_isBootstrapping && !_initialOverlayPending) {
            _paintedStandaloneIds.addAll(snapshot.processingConversations
                .where((row) => !projectedMemberIds.contains(row.id))
                .map((row) => row.id));
          }
        }
        if (defaultHome && cardsOn) {
          final projected = buildHomeCardRows(cardById.values.toList(), snapshot.processingConversations,
              now: clock.now(),
              processingTitle: context.l10n.wrappedProcessingDefault,
              liveIds: hiddenByLive,
              processingTodayOnly: _pendingWork.homeProcessingToday);
          conversationsByDate = {};
          for (final row in projected) {
            final card = cardById[row.conversation.id];
            final day = card?.startedAt == null && card != null ? unknownCardDay : row.day;
            (conversationsByDate[day] ??= []).add(row.conversation);
            projectedMemberIds.addAll(row.episodeConversationIds);
            if (row.isProcessing) projectedProcessingIds.add(row.conversation.id);
            if (row.episode != null) projectedEpisodes[row.conversation.id] = row;
          }
        }
        // Only the default view: a search or folder shows what it matched.
        final usage = context.watch<UsageProvider?>()?.subscription;
        final heldRecordings = showRecordings && !convoProvider.isSelectionModeActive
            ? lockedHeldRecordings(usage?.heldAudio, usage?.processingBacklog)
            : const <HeldAudioRecording>[];
        final heldMore = (usage?.heldAudio?.count ?? 0) - heldRecordings.length;
        final heldByDate = <DateTime, List<int>>{};
        for (final (index, recording) in heldRecordings.indexed) {
          final started = DateTime.fromMillisecondsSinceEpoch(recording.startedAt * 1000);
          (heldByDate[DateUtils.dateOnly(started)] ??= []).add(index);
        }
        final mergedDates = <DateTime>{...conversationsByDate.keys, ...recordingsByDate.keys, ...heldByDate.keys}
            .toList()
          ..sort((a, b) => b.compareTo(a));
        // Episodes beta, default view: background conversations live in the day's recap, not on Home.
        final hidingBackground = !cardsOn && episodesOn && showRecordings && !convoProvider.isSelectionModeActive;
        final builtRows = _processingFirst(
            _buildConversationListRows(
              dates: mergedDates,
              conversationsByDate: hidingBackground ? _withoutBackground(conversationsByDate) : conversationsByDate,
              recordingsByDate: recordingsByDate,
              heldByDate: heldByDate,
            ),
            projectedProcessingIds,
            enabled: defaultHome);
        final localToday = localHomeDay(clock.now());
        final withLive = episodeLive
            ? _withTodayRow(builtRows, clock.now(), _ConversationListRowKind.liveEpisode)
            : v3LiveShown
                ? _pinFirstInDay(builtRows, v3Live.id)
                : livePlaceholder
                    ? _withTodayRow(builtRows, clock.now(), _ConversationListRowKind.v3LivePlaceholder)
                    : builtRows;
        // Only the default view: a search or folder shows what it matched.
        // Default Home already projected every local entry together with server
        // rows. A second insertion can resurrect stale ready/noise entries and
        // bypass the one-row fold. Filtered views keep their adapter; capability negotiation never disables the fold.
        final rowsWithLocalProcessing = showRecordings && !convoProvider.isSelectionModeActive && !defaultHome
            ? _withProcessingRows(
                withLive,
                [
                  for (final c in snapshot.processingConversations)
                    if ((!cardsOn ||
                            (!cardById.containsKey(c.id) &&
                                !cardById.values
                                    .any((card) => card.kind == 'episode' && card.detailId == c.episodeId))) &&
                        !projectedMemberIds.contains(c.id) &&
                        (!activityOnlyFailures || !isFailedConversation(c)) &&
                        (!_pendingWork.homeProcessingToday || localHomeDay(c.startedAt ?? c.createdAt) == localToday))
                      c,
                ],
                clock.now())
            : withLive;
        final conversationRows = showManualFinish
            ? _withProcessingRows(rowsWithLocalProcessing, [manualFinish], clock.now())
            : rowsWithLocalProcessing;

        if (showRecordings &&
            !convoProvider.isSelectionModeActive &&
            !convoProvider.showDiscardedConversations &&
            !isShowingConversationSkeleton) {
          final visible = conversationRows
              .where((row) =>
                  row.kind == _ConversationListRowKind.conversation ||
                  row.kind == _ConversationListRowKind.liveEpisode ||
                  row.kind == _ConversationListRowKind.v3LivePlaceholder ||
                  row.kind == _ConversationListRowKind.processing ||
                  row.kind == _ConversationListRowKind.recording)
              .length;
          HomeRowsHealth.note(visible);
        }

        return RefreshIndicator(
          onRefresh: () async {
            HapticFeedback.mediumImpact();
            if (!cardsOn && feed?.unsupported == true) {
              await feed!.refresh();
              if (!feed.unsupported) return;
              if (!context.mounted) return;
            }
            if (cardsOn) {
              await Future.wait([
                feed.refresh(),
                context.read<LocalRecordingsProvider>().refresh(),
                if (_recapsKey.currentState != null) _recapsKey.currentState!.refresh()
              ]);
              return;
            }
            _lastLoadMoreRequestKey = null;
            if (v3On) unawaited(v3!.refresh());
            unawaited(_pendingWork.refresh());
            // Pull-to-refresh is an explicit layout boundary. Keep the held
            // projection until both reads finish, so provider notifications
            // during this refresh cannot expose half of the new grouping.
            episodes?.invalidateHome();
            if (context.read<EpisodeProvider?>() case final episodes?) unawaited(episodes.refreshLive());
            final today = DateUtils.dateOnly(clock.now());
            final from = convoProvider.groupedConversations.keys.fold<DateTime>(
              today.subtract(const Duration(days: 7)),
              (oldest, day) => day.isBefore(oldest) ? day : oldest,
            );
            final history = episodes == null
                ? Future.value(true)
                : episodes.refreshHome(from, today.add(const Duration(days: 1)), force: true);
            Provider.of<CaptureProvider>(context, listen: false).refreshInProgressConversations();
            await Future.wait([
              convoProvider.getInitialConversations(),
              history,
              Provider.of<LocalRecordingsProvider>(context, listen: false).refresh(),
              if (_recapsKey.currentState != null) _recapsKey.currentState!.refresh(),
              // Review's entry hides when caught up; a pull is how a hidden one comes back.
              if (Provider.of<ReviewProvider?>(context, listen: false) case final review?
                  when review.availability != ReviewAvailability.off)
                review.load(),
            ]);
            // The reader pulled; a refresh that failed says so above the rows it kept (§17.4).
            if (context.mounted && convoProvider.conversationsLoadFailed && convoProvider.conversations.isNotEmpty) {
              OmiFeedback.error(
                context,
                context.l10n.couldNotRefreshConversations,
                actionLabel: context.l10n.tryAgain,
                onAction: () => unawaited(convoProvider.getInitialConversations()),
              );
            }
            final historyReady = await history;
            if (mounted && historyReady) {
              if (_initialOverlayReady case final ready? when !ready.isCompleted) ready.complete();
              setState(_releaseHomeLayout);
            }
          },
          color: OmiColors.onAccent,
          backgroundColor: OmiColors.accent,
          child: CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // The live capture row: recording, a call, or a conversation being captured. With episodes
              // on, a streaming capture is the live episode row in Today instead. On v3 Home a streaming
              // capture is always the live conversation row: the server's window once it has one, and a
              // placeholder row until then (or between windows), never the pendant capture card, so the
              // two do not swap each time the live read comes back empty.
              SliverToBoxAdapter(
                child: ConversationCaptureWidget(
                    showsCall: true, deferStreamingToEpisode: episodeLive || v3Live != null || (v3Home && streaming)),
              ),
              // A declined renewal the user can still pay: one row, Update opens Stripe's billing portal.
              const SliverToBoxAdapter(child: PaymentIssueRow()),
              // A paying monthly reader whose Omi recorded nothing for 5 days: one quiet row, Check opens the device.
              const SliverToBoxAdapter(child: QuietPayerRow()),
              const SliverToBoxAdapter(child: SpeechProfileCardWidget()),
              const SliverToBoxAdapter(child: UpdateFirmwareCardWidget()),
              // Review absorbs the voice prompts; the old card shows only while Review is off.
              const SliverToBoxAdapter(child: ReviewEntryCard()),
              // Opt-in from Developer Settings. Hidden, the row is not mounted, so nothing is fetched.
              SliverToBoxAdapter(
                child: ValueListenableBuilder<bool>(
                  valueListenable: HomeDailyRecapsSetting.listenable,
                  builder: (context, shown, _) => !shown
                      ? const SizedBox.shrink()
                      : widget.loadRecaps == null
                          ? HomeDailyRecaps(key: _recapsKey)
                          : HomeDailyRecaps(key: _recapsKey, load: widget.loadRecaps!),
                ),
              ),
              // With no list rows to sit in (still loading, or nothing listed yet), the live placeholder
              // opens Today itself, the same Today header and slot it takes in the list.
              // The list below renders only when there is something to list; otherwise an empty, hero or
              // status branch takes its place (held recordings alone do not keep the list up).
              if (livePlaceholder &&
                  (_isBootstrapping ||
                      _initialOverlayPending ||
                      (conversationsByDate.values.every((list) => list.isEmpty) &&
                          !hasRecordings &&
                          !hasProcessingConversations) ||
                      !conversationRows.any((r) => r.kind == _ConversationListRowKind.v3LivePlaceholder)))
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        DateListItem(date: DateUtils.dateOnly(clock.now()), isFirst: true),
                        const V3LivePlaceholderRow(),
                      ],
                    ),
                  ),
                ),
              // With no list yet, the live episode opens Today itself.
              if (episodeLive && builtRows.isEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        DateListItem(date: DateUtils.dateOnly(clock.now()), isFirst: true),
                        const LiveEpisodeRow(),
                      ],
                    ),
                  ),
                ),
              // Typed HTTP status precedes empty/loading/hero so an outage is
              // never the new-account empty state. Unset (data) keeps production.
              // The skeleton is Home's only loading state: it stays up until the first
              // episode read settles, so no second loader replaces it.
              if (cardsOn && feed.partial)
                SliverToBoxAdapter(
                    child: feed.items.isEmpty && feed.problem != null
                        ? OmiErrorState(message: context.l10n.somethingWentWrong, onRetry: feed.refresh)
                        : OmiPartialNotice(message: context.l10n.somethingWentWrong, onRetry: feed.retry)),
              if (!cardsOn && showManualFinish && showTypedStatus && apiPhase != ApiViewPhase.empty)
                SliverToBoxAdapter(child: ConversationApiStatus(provider: convoProvider)),
              if ((_isBootstrapping && (!cardsOn || feed.items.isEmpty)) || _initialOverlayPending)
                _buildLoadingShimmer()
              else if (cardsOn && feed.items.isEmpty && feed.partial)
                const SliverToBoxAdapter(child: SizedBox.shrink())
              else if (!cardsOn &&
                  showTypedStatus &&
                  conversationsByDate.values.every((list) => list.isEmpty) &&
                  snapshot.conversations.isEmpty &&
                  !hasProcessingConversations &&
                  !hasRecordings &&
                  !convoProvider.hasActiveHomeFilter)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: ConversationApiStatus(provider: convoProvider)),
                )
              else if (!livePlaceholder &&
                  _nonDiscardedConversationCount(convoProvider) == 0 &&
                  conversationsByDate.values.every((list) => list.isEmpty) &&
                  !hasProcessingConversations &&
                  !hasRecordings &&
                  !isShowingConversationSkeleton &&
                  !convoProvider.hasActiveHomeFilter &&
                  (!cardsOn || (feed.initialized && !feed.partial)))
                // Friendly hero for brand-new users with zero conversations —
                // matches the polished Tasks empty state.
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: NoConversationsHero(
                      message: switch (snapshot.homeEmptyExplanation) {
                        HomeEmptyExplanation.tooShort => context.l10n.tooShortDesc,
                        HomeEmptyExplanation.discardedOnly => context.l10n.discardedOnlyRecording,
                        HomeEmptyExplanation.none => null,
                      },
                    ),
                  ),
                )
              else if (!livePlaceholder &&
                  conversationsByDate.values.every((list) => list.isEmpty) &&
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
              else if (conversationsByDate.values.every((list) => list.isEmpty) &&
                  !hasRecordings &&
                  !hasProcessingConversations &&
                  isShowingConversationSkeleton)
                _buildLoadingShimmer()
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(childCount: conversationRows.length + 1, (context, index) {
                    if (index == conversationRows.length) {
                      Logger.debug('loading more conversations');
                      if (cardsOn) return feed.loading ? _buildLoadMoreShimmer() : const SizedBox(height: 20);
                      if (convoProvider.isLoadingConversations) {
                        return _buildLoadMoreShimmer();
                      }
                      // A failed older page ends the list with one quiet line, not silence (X6);
                      // scrolling does not retry it on its own.
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
                      case _ConversationListRowKind.heldRecording:
                        final held = heldRecordings[row.conversationIndex];
                        return HeldRecordingLockedRow(
                          key: ValueKey('held_${held.id}'),
                          recording: held,
                          more: row.conversationIndex == heldRecordings.length - 1 ? heldMore : 0,
                        );
                      case _ConversationListRowKind.dateHeader:
                        if (v3Home && row.date != unknownCardDay && row.date.isBefore(localHomeDay(clock.now()))) {
                          return DaySummaryHeader(
                            key: ValueKey('date_${row.date.toIso8601String()}'),
                            date: row.date,
                            isFirst: row.isFirst,
                            open: widget.openDaySummary,
                          );
                        }
                        return DateListItem(
                          key: ValueKey('date_${row.date.toIso8601String()}'),
                          date: row.date,
                          label: cardsOn && row.date == unknownCardDay ? context.l10n.unknown : null,
                          isFirst: row.isFirst,
                        );
                      case _ConversationListRowKind.liveEpisode:
                        return Column(
                          key: const ValueKey('live_episode'),
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (row.isFirst) DateListItem(date: row.date, isFirst: true),
                            const LiveEpisodeRow(),
                          ],
                        );
                      case _ConversationListRowKind.v3LivePlaceholder:
                        return Column(
                          key: const ValueKey('v3_live_placeholder_row'),
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (row.isFirst) DateListItem(date: row.date, isFirst: true),
                            const V3LivePlaceholderRow(),
                          ],
                        );
                      case _ConversationListRowKind.processing:
                        return Column(
                          key: ValueKey('processing_${row.conversation!.id}'),
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (row.isFirst) DateListItem(date: row.date, isFirst: true),
                            ProcessingConversationRow(
                                conversation: row.conversation!,
                                openable: !identical(row.conversation, manualFinish),
                                step: homeStepOf(row.conversation!) ?? HomeStep.transcribing),
                          ],
                        );
                      case _ConversationListRowKind.conversation:
                        if (projectedProcessingIds.contains(row.conversation!.id)) {
                          final projectedRow = projectedEpisodes[row.conversation!.id];
                          return ProcessingConversationRow(
                            key: ValueKey('processing_${row.conversation!.id}'),
                            conversation: row.conversation!,
                            episode: projectedRow?.episode,
                            processingEpisodes: projectedRow?.processingEpisodes ?? const [],
                            step: projectedRow?.step ?? HomeStep.writingNotes,
                            count: projectedRow?.count ?? 1,
                          );
                        }
                        // Consecutive locked rows share one frosted card and one upgrade action;
                        // the run's first row draws it and the rest of the run draws nothing.
                        final lockedRun = cardsOn ? null : _lockedRunAt(conversationRows, index);
                        if (lockedRun != null) {
                          if (lockedRun.isEmpty) return const SizedBox.shrink();
                          return LockedConversationRun(
                            key: ValueKey('locked_run_${row.conversation!.id}'),
                            conversations: lockedRun,
                            date: row.date,
                          );
                        }
                        return ConversationListItem(
                          key: ValueKey(cardById[row.conversation!.id]?.id ?? row.conversation!.id),
                          conversation: row.conversation!,
                          conversationIdx: row.conversationIndex,
                          homeCard: cardById[row.conversation!.id],
                          date: row.date,
                          fillingSeconds: homeRowFilling(
                            filling,
                            row.conversation!.id,
                            projectedEpisodes[row.conversation!.id]?.episodeConversationIds,
                          ),
                          homeEpisode: projectedEpisodes[row.conversation!.id]?.isTemporaryMember == true
                              ? null
                              : projectedEpisodes[row.conversation!.id]?.episode,
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
