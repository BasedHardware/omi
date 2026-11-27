import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart' hide NotificationListener;
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/messages.dart' show ChatPageContext;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/pages/conversation_detail/widgets/live_summary_section.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/pages/episodes/live_transcript_view.dart' show LivePreviewTail;
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';
import 'package:omi/services/live_preview/live_words_hole.dart';
import 'package:omi/services/live_preview/live_words_log.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/pages/conversation_detail/widgets/streamed_lines_tail.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/pages/paywall/value_moment_paywall.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/integrations_page.dart' show IntegrationApp, IntegrationsPage;
import 'package:omi/services/audio_download_service.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/utils/share_sheet.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'conversation_detail_provider.dart';
import 'conversation_summary_selection.dart';
import 'widgets.dart' show summaryRetrySlotApplies;
import 'share.dart';
import 'conversation_live_guard.dart';
import 'share_flow.dart';
import 'test_prompts.dart';
import 'live_conversation_refresher.dart';
import 'widgets/audio_download_progress_sheet.dart';
import 'capture_group_separation.dart';
import 'widgets/calendar_event_sheets.dart';
import 'widgets/capture_recordings.dart';
import 'widgets/conversation_activity_strip.dart';
import 'widgets/conversation_action_items_section.dart' show conversationActionItemSearchMatchCount;
import 'widgets/conversation_detail_header.dart';
import 'widgets/conversation_detail_tabs.dart';
import 'widgets/detail_search_bar.dart';
import 'widgets/summary_tab.dart';
import 'widgets/ask_agent_sheet.dart';
import 'widgets/share_to_contacts_sheet.dart';
import 'widgets/summarized_apps_sheet.dart';
import 'widgets/transcript_tab.dart';
import 'package:omi/pages/held_audio/processing_backlog_view.dart';

/// Offset of the floating bottom bar from the bottom of the screen.
///
/// 32pt is the bar's resting position and already clears the iPhone home
/// indicator. Android 16 draws a 3-button navigation bar up to 48dp tall over
/// this edge-to-edge body, which covered the lower part of the bar's buttons,
/// so the bar never sits lower than the inset the window reports.
double detailFloatingBarBottom(double bottomSystemInset) => math.max(32, bottomSystemInset);

/// Height of the floating bottom bar (Ask Omi, or the player and Ask button).
const double detailFloatingBarHeight = 56;

/// How far above the safe area a toast must float to clear the floating bottom bar.
double detailToastClearance(double bottomSystemInset) =>
    detailFloatingBarBottom(bottomSystemInset) + detailFloatingBarHeight - bottomSystemInset;

/// Chooses the first useful detail tab for a conversation.
///
/// A caller-supplied tab is authoritative: search deep links use it to
/// preserve the user's context. When no tab was requested, a completed
/// conversation with transcript text but no generated summary opens on the
/// transcript so retained fragment data is immediately visible.
ConversationTab conversationDetailInitialTab(ServerConversation conversation, {ConversationTab? requested}) {
  if (requested != null) return requested;
  if (conversation.processingDeferred) return ConversationTab.transcript;
  if (conversation.status != ConversationStatus.completed) return ConversationTab.summary;

  final hasTranscript = conversation.transcriptSegments.any((segment) => segment.text.trim().isNotEmpty);
  final hasSummary = ConversationSummarySelection.select(conversation).kind != ConversationSummaryKind.empty;
  return hasTranscript && !hasSummary ? ConversationTab.transcript : ConversationTab.summary;
}

/// Tab indices of the detail page, in the order the tab row shows them (v3: Summary, Transcript).
const int _summaryTabIndex = 0;
const int _transcriptTabIndex = 1;

/// Whether the overflow menu shows developer tools (Copy Conversation ID, Test Prompt): debug
/// builds, or Developer Settings → Conversation Developer Tools (`devModeEnabled`).
@visibleForTesting
bool conversationDetailShowsDeveloperTools() => kDebugMode || SharedPreferencesUtil().devModeEnabled;

class ConversationDetailPage extends StatefulWidget {
  final ServerConversation conversation;

  /// Kept for existing callers; it no longer changes navigation (back always pops).
  final bool isFromOnboarding;
  final bool openShareToContactsOnLoad;

  /// Null lets the page choose the first useful tab after detail hydration.
  /// A non-null value preserves an explicit deep link or navigation context.
  final ConversationTab? initialTab;

  /// When set (e.g. from search match snippet), open transcript and play this moment.
  final double? initialSeekStart;
  final double? initialSeekEnd;

  const ConversationDetailPage({
    super.key,
    this.isFromOnboarding = false,
    required this.conversation,
    this.openShareToContactsOnLoad = false,
    this.initialTab,
    this.initialSeekStart,
    this.initialSeekEnd,
  });

  @override
  State<ConversationDetailPage> createState() => ConversationDetailPageState();
}

class ConversationDetailPageState extends State<ConversationDetailPage>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  final GlobalKey _shareButtonKey = GlobalKey();
  TabController? _controller;
  ConversationTab selectedTab = ConversationTab.summary;

  // Callback to seek audio to transcript segment (start, end) in wall seconds
  Future<void> Function(double start, double end)? _seekToSegmentCallback;

  // Page-owned playback state: the bar's player reports into it, the transcript
  // highlights and follows from it.
  late final ConversationPlaybackController _playbackController;

  /// Held for dispose, when the page can no longer look the provider up.
  late final ConversationDetailProvider _detailProvider;
  late final LiveConversationRefresher _liveRefresher;
  StreamSubscription<SummaryWaitAnswer>? _summaryAnswers;
  bool _isSharing = false;
  bool _reviewInterrupted = false;
  bool _isTogglingStarred = false;
  bool _isDownloadingAudio = false;
  bool _providerInitialized = false;
  late final String _routeUid;
  late final int _routeIdentityEpoch;

  void _onRouteIdentityChanged() {
    if (mounted) setState(() {});
  }

  bool _didInitialSeek = false;
  bool _hasExplicitTabSelection = false;
  bool _summaryOpenPending = false;
  bool _summaryOpenCheckQueued = false;
  bool _tabScrollInProgress = false;
  bool _tabDragStartedOnTranscript = false;
  bool _initialLiveHydrationFinished = false;
  Timer? _liveSummaryTimer;

  // Reliability experiment instant_live_text: this page has told the listening connection that its
  // transcript is on screen.
  bool _reportedTranscriptOnScreen = false;
  String? _liveSummaryInterval;
  int _liveSummaryTick = 0;
  int _summaryOpen = 0;
  int _claimedSummaryOpen = 0;
  ServerConversation? _summaryOpenSnapshot;
  bool _liveEndRequested = false;
  bool _resultViewedRecorded = false;

  /// When the summary of this conversation first showed; leaving after [ValueMomentPaywall.summaryDwell]
  /// is the first-summary moment.
  DateTime? _summaryShownAt;

  // Search functionality
  bool _isSearching = false;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();
  int _currentSearchIndex = 0;
  int _totalSearchResults = 0;

  /// The Summary tab's matches that belong to the note itself; the tab's
  /// action-item section's matches follow them, so this is the section's
  /// offset into the tab's results.
  int _summaryContentSearchResults = 0;
  final List<(Timer, Completer<void>)> _ownedDelays = [];
  final _separation = CaptureGroupSeparationController();

  void _updateSearchResults() {
    if (_searchQuery.isEmpty) {
      _totalSearchResults = 0;
      _summaryContentSearchResults = 0;
      _currentSearchIndex = 0;
      return;
    }

    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final query = _searchQuery.toLowerCase();
    int countIn(String text) {
      int count = 0;
      int index = 0;
      while ((index = text.indexOf(query, index)) != -1) {
        count++;
        index += query.length;
      }
      return count;
    }

    int count = 0;
    _summaryContentSearchResults = 0;
    if (selectedTab == ConversationTab.transcript) {
      for (var segment in provider.conversation.transcriptSegments) {
        count += countIn(segment.text.toLowerCase());
      }
    } else if (selectedTab == ConversationTab.summary) {
      final summarySelection = provider.getSummarySelection();
      if (summarySelection.content.isNotEmpty) {
        _summaryContentSearchResults = countIn(summarySelection.content.decodeString.toLowerCase());
      }
      // The tab renders its action items after the note; their matches count
      // toward the tab's total and are navigated inside the section.
      count = _summaryContentSearchResults +
          conversationActionItemSearchMatchCount(provider.conversation.structured.actionItems, _searchQuery);
    }

    _totalSearchResults = count;
    _currentSearchIndex = count > 0 ? 1 : 0;
  }

  void _navigateSearch(bool next) {
    if (_totalSearchResults == 0) return;

    setState(() {
      if (next) {
        _currentSearchIndex = _currentSearchIndex >= _totalSearchResults ? 1 : _currentSearchIndex + 1;
      } else {
        _currentSearchIndex = _currentSearchIndex <= 1 ? _totalSearchResults : _currentSearchIndex - 1;
      }
    });
  }

  int getCurrentResultIndexForHighlighting() {
    return _currentSearchIndex - 1;
  }

  void _closeSearch() {
    setState(() {
      _isSearching = false;
      _searchQuery = '';
      _searchController.clear();
      _totalSearchResults = 0;
      _currentSearchIndex = 0;
      _searchFocusNode.unfocus();
    });
  }

  void _closeSearchIfEmpty() {
    if (_isSearching && _searchQuery.isEmpty) _closeSearch();
  }

  static ConversationTab _tabForIndex(int index) =>
      index == _transcriptTabIndex ? ConversationTab.transcript : ConversationTab.summary;

  static int _indexForTab(ConversationTab tab) => switch (tab) {
        ConversationTab.transcript => _transcriptTabIndex,
        ConversationTab.summary => _summaryTabIndex,
      };

  /// Brings the Summary tab forward. A reprocess started elsewhere (the ⋯ menu on Transcript,
  /// a failed-transcript retry) shows its progress and, with the v2 gate, its failure card there.
  void _openSummaryTab() {
    _summaryOpenPending = false;
    _hasExplicitTabSelection = true;
    setState(() => selectedTab = ConversationTab.summary);
    _controller?.animateTo(_summaryTabIndex);
  }

  void _createTabController({required int initialIndex}) {
    _controller = TabController(length: 2, vsync: this, initialIndex: initialIndex);
    _controller!.addListener(_onTabChanged);
  }

  bool _summaryTabIsVisible() {
    final controller = _controller;
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    return mounted &&
        (lifecycle == null || lifecycle == AppLifecycleState.resumed) &&
        controller != null &&
        controller.index == _summaryTabIndex &&
        !controller.indexIsChanging &&
        controller.offset.abs() < 0.001 &&
        !_tabScrollInProgress &&
        !_liveEndRequested &&
        ModalRoute.isCurrentOf(context) != false &&
        SharedPreferencesUtil().uid == _routeUid &&
        AnalyticsManager.identityEpoch == _routeIdentityEpoch;
  }

  bool get _viewingLiveSummary {
    final c = _detailProvider.conversationOrNull;
    return c != null &&
        c.id == widget.conversation.id &&
        _isLiveV3(c) &&
        !c.isLocked &&
        !c.discarded &&
        c.v3?.homeHidden != true &&
        LiveSummarySection.speechEligible(c) &&
        _detailProvider.hasHydratedDetail(c.id) &&
        _summaryTabIsVisible();
  }

  void _syncLiveSummaryTimer() {
    if (!_viewingLiveSummary) {
      _liveSummaryTimer?.cancel();
      _liveSummaryTimer = null;
      _liveSummaryInterval = null;
      return;
    }
    _liveSummaryInterval ??= const Uuid().v4();
    _liveSummaryTimer ??= Timer.periodic(const Duration(minutes: 5), (_) {
      if (_viewingLiveSummary) {
        setState(() => _liveSummaryTick++);
      } else {
        _syncLiveSummaryTimer();
      }
    });
  }

  String? _liveSummaryIntervalForDispatch() => _viewingLiveSummary ? _liveSummaryInterval : null;

  bool _claimSummaryOpen(int open) {
    if (open != _summaryOpen || open <= _claimedSummaryOpen) return false;
    _claimedSummaryOpen = open;
    final snapshot = _summaryOpenSnapshot;
    _summaryOpenSnapshot = null;
    return _summaryTabIsVisible() && identical(snapshot, _detailProvider.conversationOrNull);
  }

  void _onDetailTabTap(int index) {
    _hasExplicitTabSelection = true;
    _summaryOpenPending = index == _summaryTabIndex;
    _scheduleSummaryOpen();
  }

  bool _onDetailTabScroll(ScrollNotification notification) {
    if (notification.depth != 0 || notification.metrics is! PageMetrics) return false;
    if (notification is ScrollStartNotification) {
      _tabScrollInProgress = true;
      if (notification.dragDetails != null) {
        _summaryOpenPending = false;
        _tabDragStartedOnTranscript = _controller?.index == _transcriptTabIndex;
      }
    } else if (notification is ScrollEndNotification) {
      _tabScrollInProgress = false;
      if (_tabDragStartedOnTranscript && _controller?.index == _summaryTabIndex) {
        _hasExplicitTabSelection = true;
        _summaryOpenPending = true;
      }
      _tabDragStartedOnTranscript = false;
      _scheduleSummaryOpen();
    }
    _syncLiveSummaryTimer();
    return false;
  }

  void _scheduleSummaryOpen() {
    if (!_summaryOpenPending || _summaryOpenCheckQueued || !_initialLiveHydrationFinished) return;
    _summaryOpenCheckQueued = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _summaryOpenCheckQueued = false;
      if (!mounted || !_summaryOpenPending) return;
      if (ModalRoute.isCurrentOf(context) == false) {
        _summaryOpenPending = false;
        return;
      }
      if (!_summaryTabIsVisible()) return;
      _summaryOpenPending = false;
      final current = _detailProvider.conversationOrNull;
      if (current == null ||
          !_detailProvider.hasHydratedDetail(current.id) ||
          current.id != widget.conversation.id ||
          !_isLiveV3(current)) {
        return;
      }
      setState(() {
        _summaryOpenSnapshot = current;
        _summaryOpen++;
      });
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _onTabChanged() {
    _syncLiveSummaryTimer();
    _scheduleSummaryOpen();
    final tab = _tabForIndex(_controller!.index);
    if (tab == selectedTab) return;
    setState(() {
      selectedTab = tab;
      PlatformManager.instance.analytics.conversationDetailTabChanged(switch (tab) {
        ConversationTab.transcript => 'Transcript',
        ConversationTab.summary => 'Summary',
      });
      if (_searchQuery.isNotEmpty) _updateSearchResults();
    });
  }

  @override
  void initState() {
    super.initState();
    _routeUid = SharedPreferencesUtil().uid;
    _routeIdentityEpoch = AnalyticsManager.identityEpoch;
    AnalyticsManager.identityChanges.addListener(_onRouteIdentityChanged);
    _detailProvider = context.read<ConversationDetailProvider>();
    _liveRefresher = LiveConversationRefresher(
        read: () => _detailProvider.conversationOrNull,
        refresh: _detailProvider.refreshConversation,
        inFront: () => mounted && ModalRoute.of(context)?.isCurrent != false)
      ..start();
    // Reliability experiment fast_end_feedback: after this conversation is ended (from this page or any
    // other way), the app's waiting requests return it when it is committed with its outline and when its
    // summary is stored; each answer lands through the ordinary refresh. Off, nothing is ever emitted.
    _summaryAnswers = Provider.of<ConversationsV3Provider?>(context, listen: false)?.summaryAnswers.listen((answer) {
      if (!mounted || _detailProvider.conversationOrNull?.id != answer.conversationId) return;
      unawaited(_detailProvider.refreshConversation(read: (_) async => answer.result));
    });
    WidgetsBinding.instance.addObserver(this);
    unawaited(
      SiriIntegration.instance.setCurrentScreen("/conversation/${widget.conversation.id}", widget.conversation.id),
    );
    unawaited(SiriIntegration.instance.donateUiAction('conversation', widget.conversation.id));
    unawaited(SummaryGenerationV2Gate.refresh());

    // The supplied conversation can be a list projection whose app results
    // are hydrated after the first frame. Start on Summary, then select the
    // transcript only once the final summary state is known.
    _playbackController = ConversationPlaybackController()..updateSegments(widget.conversation.transcriptSegments);
    // A conversation still in progress opens on its transcript, where its content is; its Summary tab
    // only says the summary comes when it ends. When it ends the page does not switch tabs.
    final liveAtOpen = _isLiveV3(widget.conversation);
    _createTabController(
        initialIndex:
            _indexForTab(widget.initialTab ?? (liveAtOpen ? ConversationTab.transcript : ConversationTab.summary)));
    if (liveAtOpen) _hasExplicitTabSelection = true;
    selectedTab = _tabForIndex(_controller!.index);

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;

      final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
      final identityEpoch = AnalyticsManager.identityEpoch;

      // Ensure the provider has the conversation data from the widget parameter
      provider.setCachedConversation(widget.conversation);
      _providerInitialized = true;

      // Find the proper date and index for this conversation in the grouped conversations
      final result = conversationProvider.getConversationDateAndIndex(widget.conversation);
      if (result != null) {
        final (date, _) = result;
        provider.updateConversation(widget.conversation.id, date);
      } else {
        final effectiveDate = widget.conversation.startedAt ?? widget.conversation.createdAt;
        provider.selectedDate = conversationLocalDayKey(effectiveDate);
      }

      await provider.initConversation();
      _recordResultViewed(provider, identityEpoch);
      if (_awaitsTranscript(provider.conversation) || _isLiveV3(provider.conversation)) {
        // Opened from a copy without its lines (a search hit, a locked-then-unlocked row): fetch the
        // full conversation and let the Transcript tab say it is loading, or offer Try Again.
        unawaited(
          provider.refreshConversation(trackLoad: true).then((hydrated) {
            if (!mounted || identityEpoch != AnalyticsManager.identityEpoch) return;
            _initialLiveHydrationFinished = true;
            if (!hydrated) _summaryOpenPending = false;
            _scheduleSummaryOpen();
            _selectInitialTabIfNeeded(provider.conversation);
            _recordResultViewed(provider, identityEpoch);
          }),
        );
      } else if (provider.conversation.transcriptCarried) {
        // The lines on screen were kept across a list refresh and may be stale: re-read quietly.
        unawaited(provider.refreshConversation());
      } else if (provider.conversation.appResults.isEmpty) {
        final conversationId = provider.conversation.id;
        if (conversationProvider.getConversationDateAndIndexById(conversationId) != null) {
          // The initial list payload is enough to render the detail page. Fill
          // in omitted app results after the first usable frame instead of
          // holding the destination's startup sequence on this request. The
          // provider re-locates the conversation by ID after the await because
          // refreshes can reorder or replace the grouped list meanwhile.
          unawaited(_refreshDetailsAndSelectInitialTab(conversationProvider, provider, conversationId, identityEpoch));
        } else {
          provider.updateConversation(provider.conversation.id, provider.selectedDate);
          _selectInitialTabIfNeeded(provider.conversation);
          unawaited(provider.refreshConversation());
        }
      } else {
        _selectInitialTabIfNeeded(provider.conversation);
        unawaited(provider.refreshConversation());
      }

      // Auto-open share to contacts sheet if requested (from important conversation notification)
      if (widget.openShareToContactsOnLoad && mounted) {
        // Small delay to ensure the page is fully rendered
        await _delay(const Duration(milliseconds: 500));
        if (mounted) {
          _showShareToContactsBottomSheet();
        }
      }
    });
  }

  /// A conversation whose lines should exist but are not in the copy the page opened with.
  static bool _awaitsTranscript(ServerConversation conversation) =>
      conversation.transcriptSegments.isEmpty &&
      conversation.photos.isEmpty &&
      conversation.externalIntegration == null &&
      !conversation.isLocked &&
      !conversation.discarded;

  void _recordResultViewed(ConversationDetailProvider provider, int identityEpoch) {
    if (_resultViewedRecorded || !mounted || identityEpoch != AnalyticsManager.identityEpoch) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_resultViewedRecorded || !mounted || identityEpoch != AnalyticsManager.identityEpoch) return;
      final route = ModalRoute.of(context);
      if (route != null && !route.isCurrent) return;
      final conversation = provider.conversationOrNull;
      if (conversation == null ||
          conversation.id.isEmpty ||
          conversation.id != widget.conversation.id ||
          !_hasRenderedDetailContent(provider)) {
        return;
      }
      _resultViewedRecorded = true;
      final usage = context.read<UsageProvider?>();
      if (selectedTab == ConversationTab.summary &&
          (usage == null || ValueMomentPaywall.mayOffer(usage, PaywallMoment.ahaFirstSummary))) {
        _summaryShownAt = DateTime.now();
      }
      ProductTelemetry.instance.value(
        ProductValue.resultViewed,
        surface: ProductSurface.conversationDetail,
        objectId: RecordReference.fromId(conversation.id),
      );
    });
  }

  bool _hasRenderedDetailContent(ConversationDetailProvider provider) {
    final conversation = provider.conversationOrNull;
    if (conversation == null) return false;
    return switch (selectedTab) {
      ConversationTab.transcript => conversation.transcriptSegments.any((segment) => segment.text.trim().isNotEmpty),
      ConversationTab.summary => provider.getSummarySelection().content.trim().isNotEmpty,
    };
  }

  Future<void> _refreshDetailsAndSelectInitialTab(
    ConversationProvider conversationProvider,
    ConversationDetailProvider provider,
    String conversationId,
    int identityEpoch,
  ) async {
    if (identityEpoch != AnalyticsManager.identityEpoch) return;
    try {
      await conversationProvider.updateSearchedConvoDetails(conversationId);
    } catch (_) {
      // The list projection is still valid enough to render. Apply the same
      // fallback selection below if the detail refresh is unavailable.
    }
    if (!mounted ||
        identityEpoch != AnalyticsManager.identityEpoch ||
        provider.conversationOrNull?.id != conversationId) {
      return;
    }
    provider.updateConversation(conversationId, provider.selectedDate);
    _selectInitialTabIfNeeded(provider.conversation);
    _recordResultViewed(provider, identityEpoch);
  }

  void _selectInitialTabIfNeeded(ServerConversation conversation) {
    if (!mounted || widget.initialTab != null || _hasExplicitTabSelection || _controller?.index != _summaryTabIndex) {
      return;
    }
    if (conversationDetailInitialTab(conversation) != ConversationTab.transcript) return;
    setState(() {
      selectedTab = ConversationTab.transcript;
    });
    _controller?.animateTo(_transcriptTabIndex);
  }

  void _showActionItemInTranscript(List<String> sourceSegmentIds) {
    final provider = context.read<ConversationDetailProvider>();
    TranscriptSegment? target;
    for (final segment in provider.conversation.transcriptSegments) {
      if (sourceSegmentIds.contains(segment.id)) {
        target = segment;
        break;
      }
    }
    setState(() {
      selectedTab = ConversationTab.transcript;
      _hasExplicitTabSelection = true;
    });
    _controller?.animateTo(_transcriptTabIndex);
    final resolvedTarget = target;
    if (resolvedTarget != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (mounted && _seekToSegmentCallback != null) {
          await _seekToSegmentCallback!(resolvedTarget.start, resolvedTarget.end);
        }
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _syncLiveSummaryTimer();
    if (state != AppLifecycleState.resumed) {
      _summaryOpenPending = false;
      _tabDragStartedOnTranscript = false;
    }
    if (state == AppLifecycleState.paused) {
      _detailProvider.confirmSpeakerLabelingSession(conversationId: widget.conversation.id);
    } else if (state == AppLifecycleState.resumed) {
      // The list refresh on resume does not carry the transcript; re-read what is on screen.
      final open = _detailProvider.conversationOrNull;
      unawaited(_detailProvider.refreshConversation(trackLoad: open != null && _isLiveV3(open)));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    AnalyticsManager.identityChanges.removeListener(_onRouteIdentityChanged);
    final summaryShownAt = _summaryShownAt;
    if (summaryShownAt != null && DateTime.now().difference(summaryShownAt) >= ValueMomentPaywall.summaryDwell) {
      ValueMomentPaywall.offer(PaywallMoment.ahaFirstSummary,
          conversation: _detailProvider.conversationOrNull ?? widget.conversation);
    }
    // Leaving mid-pass auto-confirms it: one summary update for the labels already saved.
    _detailProvider.leaveSpeakerLabelingSession(widget.conversation.id);
    unawaited(SiriIntegration.instance.setCurrentScreen("", null));
    _cancelOwnedTimers();
    if (_reportedTranscriptOnScreen) {
      _reportedTranscriptOnScreen = false;
      ListenClientState.instance.capturePageClosed();
    }
    _liveSummaryTimer?.cancel();
    _liveRefresher.dispose();
    unawaited(_summaryAnswers?.cancel());
    _separation.dispose();
    _controller?.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
    _playbackController.dispose();
    super.dispose();
  }

  /// Test seam for the cancel-completes-waiter contract. Production callers use [_delay].
  @visibleForTesting
  Future<void> ownedDelayForTesting(Duration duration) => _delay(duration);

  Future<void> _delay(Duration duration) {
    if (!mounted) return Future.value();
    final completer = Completer<void>();
    late final Timer timer;
    timer = Timer(duration, () {
      _ownedDelays.remove((timer, completer));
      if (!completer.isCompleted) completer.complete();
    });
    _ownedDelays.add((timer, completer));
    return completer.future;
  }

  void _cancelOwnedTimers() {
    for (final (timer, completer) in _ownedDelays) {
      timer.cancel();
      // Complete normally: `await _delay` sits in audio cleanup's try/finally.
      // An error would look like a download failure and arm another delay in catch.
      if (!completer.isCompleted) completer.complete();
    }
    _ownedDelays.clear();
  }

  /// Show the share to contacts bottom sheet
  void _showShareToContactsBottomSheet() {
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    showShareToContactsBottomSheet(context, provider.conversation);
  }

  String _getTabTitle(BuildContext context, ConversationTab tab) {
    switch (tab) {
      case ConversationTab.transcript:
        return context.l10n.transcriptTab;
      case ConversationTab.summary:
        return context.l10n.conversationTab;
    }
  }

  Future<void> _maybePlayInitialSeek() async {
    if (_didInitialSeek || !mounted) return;
    final start = widget.initialSeekStart;
    if (start == null || _seekToSegmentCallback == null) return;
    _didInitialSeek = true;
    final end = widget.initialSeekEnd ?? start;
    if (selectedTab != ConversationTab.transcript) {
      setState(() {
        selectedTab = ConversationTab.transcript;
      });
      _controller?.animateTo(_transcriptTabIndex);
    }
    try {
      await _seekToSegmentCallback!(start, end);
      if (mounted) HapticFeedback.lightImpact();
    } catch (_) {
      // Audio may be unavailable offline; search still opened the transcript tab.
    }
  }

  void _openRecordings(List<CaptureRecording> recordings) {
    showCaptureRecordingsSheet(
      context,
      recordings: recordings,
      controller: _separation,
      onOpen: _openRecording,
      onSeparate: _separateRecording,
    );
  }

  /// Opens another device's recording of this event: the loaded row when the
  /// list has it (even hidden behind the event's row), otherwise a fetch.
  Future<void> _openRecording(CaptureRecording recording) async {
    final list = context.read<ConversationProvider>();
    final target = await CaptureGroupPresentation.resolveMember(
      recording.id,
      loaded: list.conversations.followedBy(list.searchedConversations),
      fetch: getConversationById,
    );
    if (!mounted) return;
    if (target == null) {
      OmiFeedback.error(context, context.l10n.captureRecordingOpenFailed);
      return;
    }
    Navigator.pushReplacement(
      context,
      omiPageRoute(
        builder: (_) => ConversationDetailPage(
          conversation: target,
          isFromOnboarding: widget.isFromOnboarding,
          initialTab: selectedTab,
        ),
      ),
    );
  }

  /// Separation is sticky on the server; afterwards the detail and the list
  /// reload so both show the new membership.
  Future<bool> _separateRecording(CaptureRecording recording) {
    trackConversationAction(ConversationActionAction.separate, ConversationActionSurface.detailBody);
    final detail = context.read<ConversationDetailProvider>();
    final list = context.read<ConversationProvider>();
    return _separation.separate(
      recording.id,
      reload: () async {
        await detail.refreshConversation();
        await (list.hasActiveSearch ? list.searchConversations(list.previousQuery) : list.forceRefreshConversations());
      },
    );
  }

  static const _overflowActions = {
    'copy_transcript': ConversationActionAction.copyTranscript,
    'export_transcript': ConversationActionAction.exportTranscript,
    'copy_summary': ConversationActionAction.copySummary,
    'download_audio': ConversationActionAction.shareAudio,
    'test_prompt': ConversationActionAction.testPrompt,
    'reprocess': ConversationActionAction.reprocess,
    'link_event': ConversationActionAction.linkEvent,
    'copy_conversation_id': ConversationActionAction.copyConversationId,
    'rename': ConversationActionAction.rename,
    'move_to_folder': ConversationActionAction.moveFolder,
    'visibility': ConversationActionAction.visibility,
    'recordings': ConversationActionAction.recordingsOpen,
    'delete': ConversationActionAction.delete,
  };

  void _handleMenuSelection(BuildContext context, String value, ConversationDetailProvider provider) async {
    if (refuseWhileLive(context, provider.conversation, value)) return; // X11
    // Track the menu action selection
    PlatformManager.instance.analytics.conversationThreeDotsMenuActionSelected(
      conversationId: provider.conversation.id,
      action: value,
    );

    final tracked = _overflowActions[value];
    if (tracked != null) trackConversationAction(tracked, ConversationActionSurface.overflow);

    switch (value) {
      case 'copy_transcript':
        _copyContent(context, provider.conversation.getTranscript(generate: true), context.l10n.transcript);
        break;
      case 'export_transcript':
        await _exportTranscript(provider);
        break;
      case 'copy_summary':
        // Copy the source the reader put on screen (a chip can show Omi while the canonical
        // selection is still a template's result), not the canonical selection.
        _copyContent(context, provider.getDisplayedSummarySelection().content, context.l10n.summary);
        break;
      case 'download_audio':
        await _downloadAudio(context, provider);
        break;
      case 'test_prompt':
        routeToPage(context, TestPromptsPage(conversation: provider.conversation));
        break;
      case 'reprocess':
        if (provider.loadingReprocessConversation) break;
        if (!context.read<ConnectivityProvider>().isConnected) {
          ConnectivityProvider.showNoInternetDialog(context);
          break;
        }
        // The Summary tab is the single progress and (with the v2 gate) failure surface, so a
        // request started from the ⋯ menu while Transcript is open moves there.
        _openSummaryTab();
        await provider.reprocessConversation();
        break;
      case 'link_event':
        _handleLinkEvent(context, provider);
        break;
      case 'copy_conversation_id':
        _copyContent(context, provider.conversation.id, null);
        break;
      case 'rename':
        final controller = provider.titleController;
        provider.titleFocusNode?.requestFocus();
        if (controller != null)
          controller.selection = TextSelection(baseOffset: 0, extentOffset: controller.text.length);
        break;
      case 'move_to_folder':
        await showConversationFolderSheet(context, provider.conversation, source: 'detail_page_menu');
        break;
      case 'visibility':
        ConversationVisibilitySheet.show(context, provider.conversation);
        break;
      case 'recordings':
        final recordings = CaptureGroupPresentation.recordings(provider.conversation);
        if (recordings.isNotEmpty) _openRecordings(recordings);
        break;
      case 'delete':
        _handleDelete(context, provider);
        break;
    }
  }

  Future<void> _handleLinkEvent(BuildContext context, ConversationDetailProvider provider) async {
    final integrationProvider = Provider.of<IntegrationProvider>(context, listen: false);
    final isConnected = integrationProvider.hasLoaded
        ? integrationProvider.isAppConnected(IntegrationApp.googleCalendar)
        : SharedPreferencesUtil().getBool('google_calendar_connected');

    if (isConnected) {
      await showLinkEventSheet(context);
      return;
    }
    final connect = await showOmiConfirm(
      context,
      title: context.l10n.googleCalendarNotConnected,
      message: context.l10n.googleCalendarConnectPrompt,
      confirmLabel: context.l10n.connect,
    );
    if (connect && context.mounted) routeToPage(context, const IntegrationsPage());
  }

  /// One delete path with the list (D5): confirm unless opted out, close the page, then the list
  /// shows Undo while the provider holds the server delete back.
  Future<void> _handleDelete(BuildContext context, ConversationDetailProvider provider) async {
    HapticFeedback.mediumImpact();
    if (!await confirmConversationDelete(context) || !context.mounted) return;
    final conversation = provider.conversation;
    final listContext = Navigator.of(context).context;
    Navigator.pop(context, {'deleted': true}); // Close detail page
    unawaited(deleteConversationsWithUndo(listContext, [conversation]));
  }

  void _copyContent(BuildContext context, String content, String? what) {
    HapticFeedback.lightImpact();
    OmiClipboard.copy(context, content, what: what);
  }

  Future<void> _downloadAudio(BuildContext context, ConversationDetailProvider provider) async {
    if (!mounted) return;

    setState(() {
      _isDownloadingAudio = true;
    });

    final audioFileCount = provider.conversation.audioFiles.length;
    final startTime = DateTime.now();

    // Track share start
    PlatformManager.instance.analytics.audioShareStarted(
      conversationId: provider.conversation.id,
      audioFileCount: audioFileCount,
    );

    AudioDownloadService? service;
    // The sheet pops itself with its own context; Cancel, back and the scrim stop the download.
    final sheet = AudioDownloadSheetHandle.show(context, onCancel: () => service?.dispose());

    void showFailure() {
      if (!context.mounted) return;
      OmiFeedback.error(
        context,
        context.l10n.audioDownloadFailed,
        actionLabel: context.l10n.tryAgain,
        onAction: () => _downloadAudio(context, provider),
      );
    }

    try {
      service = AudioDownloadService();

      final file = await service.downloadAndCombineAudio(
        provider.conversation,
        onProgress: (progress) => sheet.progress.value = progress,
        onStageChange: (stage) {
          sheet.state.value = switch (stage) {
            AudioDownloadStage.preparing => AudioDownloadState.preparing,
            AudioDownloadStage.downloading => AudioDownloadState.downloading,
            AudioDownloadStage.processing => AudioDownloadState.processing,
          };
        },
      );
      if (sheet.cancelled) return;

      if (file != null) {
        sheet.state.value = AudioDownloadState.success;
        await _delay(const Duration(milliseconds: 500));
        sheet.close();
        if (sheet.cancelled) return;

        final mimeType = file.path.endsWith('.mp3') ? 'audio/mpeg' : 'audio/wav';
        await SharePlus.instance.share(
          ShareParams(
            files: [XFile(file.path, mimeType: mimeType)],
            sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
          ),
        );

        // Track successful completion
        final durationSeconds = DateTime.now().difference(startTime).inSeconds;
        PlatformManager.instance.analytics.audioShareCompleted(
          conversationId: provider.conversation.id,
          audioFileCount: audioFileCount,
          wasCombined: audioFileCount > 1,
          durationSeconds: durationSeconds,
        );

        await service.cleanup();
      } else {
        sheet.close();
        PlatformManager.instance.analytics.audioShareFailed(
          conversationId: provider.conversation.id,
          errorMessage: 'No audio files available',
        );
        showFailure();
      }
    } catch (e) {
      Logger.debug('Error downloading audio: $e');
      sheet.close();
      if (!sheet.cancelled) {
        PlatformManager.instance.analytics.audioShareFailed(
          conversationId: provider.conversation.id,
          errorMessage: e.toString(),
        );
        showFailure();
      }
    } finally {
      sheet.close();
      service?.dispose();
      if (mounted) {
        setState(() {
          _isDownloadingAudio = false;
        });
      }
    }
  }

  Future<void> _toggleStarred(ConversationDetailProvider provider) async {
    setState(() => _isTogglingStarred = true);
    HapticFeedback.mediumImpact();
    try {
      final newStarredState = !provider.conversation.starred;
      final success = await setConversationStarred(provider.conversation.id, newStarredState);
      if (!mounted) return;
      if (success) {
        provider.conversation.starred = newStarredState;
        context.read<ConversationProvider>().updateConversationInSortedList(provider.conversation);
        PlatformManager.instance.analytics.conversationStarToggled(
          conversation: provider.conversation,
          starred: newStarredState,
          source: 'detail_page_button',
        );
      } else {
        OmiFeedback.error(context, context.l10n.failedToUpdateStarred);
      }
    } catch (e) {
      Logger.debug('Failed to toggle starred status: $e');
      if (mounted) OmiFeedback.error(context, context.l10n.failedToUpdateStarred);
    } finally {
      if (mounted) setState(() => _isTogglingStarred = false);
    }
  }

  /// Shares the conversation's link. A private conversation is made public only after the reader
  /// agrees ("Anyone with the link can view"), and goes back to private if the share sheet reports
  /// that it was dismissed without sharing.
  Future<void> _shareConversation(ConversationDetailProvider provider) async {
    if (refuseWhileLive(context, provider.conversation, 'share')) return; // X11
    HapticFeedback.mediumImpact();
    final conversation = provider.conversation;
    final end = await runConversationShare(
      wasPrivate: conversation.visibility != ConversationVisibility.shared,
      confirm: () async {
        final confirmed = await showOmiConfirm(
          context,
          title: context.l10n.shareConversationQuestion,
          message: context.l10n.anyoneWithLinkCanView,
          confirmLabel: context.l10n.share,
        );
        if (confirmed && mounted) setState(() => _isSharing = true);
        return confirmed && mounted;
      },
      setVisibility: (visibility) => setConversationVisibility(conversation.id, visibility: visibility.value),
      onVisibility: (visibility) {
        if (mounted) provider.updateVisibilityLocally(visibility);
      },
      openSheet: () async {
        if (mounted) setState(() => _isSharing = true);
        final origin = shareSheetOrigin(_shareButtonKey);
        // The sheet is up once the call is made; the button stops spinning while it is shown.
        final result = shareConversationLink(conversation, sharePositionOrigin: origin);
        await _delay(const Duration(milliseconds: 150));
        if (mounted) setState(() => _isSharing = false);
        return (await result).status;
      },
    );
    if (!mounted) return;
    if (_isSharing) setState(() => _isSharing = false);
    showShareFlowEnd(context, end, makePrivate: () => _makePrivate(provider));
  }

  Future<void> _makePrivate(ConversationDetailProvider provider) async {
    final ok =
        await setConversationVisibility(provider.conversation.id, visibility: ConversationVisibility.private_.value);
    if (!mounted) return;
    if (ok) {
      provider.updateVisibilityLocally(ConversationVisibility.private_);
      OmiFeedback.confirm(context, context.l10n.onlyYouCanSeeConversation);
    } else {
      showShareFlowEnd(context, ShareFlowEnd.stillPublic, makePrivate: () => _makePrivate(provider));
    }
  }

  /// Writes the full transcript to a text file, then opens the share sheet with it. The file is
  /// written first so a failure lands here, not as an unhandled error behind the sheet.
  Future<void> _exportTranscript(ConversationDetailProvider provider) async {
    if (_isSharing) return; // one export or share at a time, Try Again included
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final origin = shareSheetOrigin(_shareButtonKey);
    setState(() => _isSharing = true);
    try {
      final conversation = provider.conversation;
      final file = await writeConversationTranscript(conversation, dates: dates, l10n: l10n);
      if (!mounted) return;
      setState(() => _isSharing = false);
      await shareConversationTranscriptFile(file, conversation, sharePositionOrigin: origin);
    } catch (e) {
      Logger.debug('Failed to export transcript: $e');
      if (mounted) {
        OmiFeedback.error(context, l10n.exportFailedTryAgain,
            actionLabel: l10n.tryAgain, onAction: () => _exportTranscript(provider));
      }
    } finally {
      if (mounted && _isSharing) setState(() => _isSharing = false);
    }
  }

  List<PullDownMenuEntry> _menuItems(BuildContext context, ConversationDetailProvider provider) {
    final l10n = context.l10n;
    final showDeveloperTools = conversationDetailShowsDeveloperTools();
    final conversation = provider.conversation;
    final hasRecordings = CaptureGroupPresentation.recordings(conversation).isNotEmpty;
    // Still going: nothing that writes, edits, shares or deletes an unfinished conversation (the Home
    // row refuses delete and edits while capture writes it too). Search, Ask, copying and exporting
    // the transcript so far, recordings and developer tools stay.
    final live = _isLiveV3(conversation);
    final summarySelection = provider.getSummarySelection();
    final summaryApp =
        summarySelection.isApp ? provider.appsList.where((app) => app.id == summarySelection.appId).firstOrNull : null;
    // Grouped, with large dividers between groups: how the summary is written, then organising
    // the conversation, then finding and copying its words; developer tools (when on) sit last
    // before Delete. Star and Share live in the top bar.
    final summaryGroup = <PullDownMenuEntry>[
      if (!conversation.discarded && !live) ...[
        PullDownMenuItem(
          title: l10n.summaryTemplate,
          subtitle: summarySelection.isApp ? (summaryApp?.name ?? l10n.unknownApp) : null,
          iconWidget: const FaIcon(FontAwesomeIcons.wandMagicSparkles, size: 16),
          onTap: () {
            PlatformManager.instance.analytics.conversationThreeDotsMenuActionSelected(
              conversationId: conversation.id,
              action: 'summary_template',
            );
            showSummarizedAppsSheet(context);
          },
        ),
        PullDownMenuItem(
          title: l10n.reprocessConversation,
          iconWidget: const FaIcon(FontAwesomeIcons.arrowsRotate, size: 16),
          onTap:
              provider.loadingReprocessConversation ? null : () => _handleMenuSelection(context, 'reprocess', provider),
        ),
      ],
    ];
    final organizeGroup = <PullDownMenuEntry>[
      if (!conversation.discarded && !live)
        PullDownMenuItem(
          title: l10n.renameConversation,
          iconWidget: const FaIcon(FontAwesomeIcons.pen, size: 16),
          onTap: () => _handleMenuSelection(context, 'rename', provider),
        ),
      if (!live) ...[
        PullDownMenuItem(
          title: l10n.moveToFolder,
          iconWidget: const FaIcon(FontAwesomeIcons.folder, size: 16),
          onTap: () => _handleMenuSelection(context, 'move_to_folder', provider),
        ),
        PullDownMenuItem(
          title: l10n.visibility,
          iconWidget: FaIcon(
            provider.conversation.visibility == ConversationVisibility.private_
                ? FontAwesomeIcons.lock
                : FontAwesomeIcons.globe,
            size: 16,
          ),
          onTap: () => _handleMenuSelection(context, 'visibility', provider),
        ),
      ],
      if (provider.conversation.calendarEvent == null && !live)
        PullDownMenuItem(
          title: l10n.linkEvent,
          iconWidget: ClipRRect(
            borderRadius: const BorderRadius.all(Radius.circular(4)),
            child: Image.asset('assets/integration_app_logos/google-calendar.png', width: 17, height: 17),
          ),
          onTap: () => _handleMenuSelection(context, 'link_event', provider),
        ),
      if (hasRecordings)
        PullDownMenuItem(
          title: l10n.recordings,
          iconWidget: const FaIcon(FontAwesomeIcons.layerGroup, size: 16),
          onTap: () => _handleMenuSelection(context, 'recordings', provider),
        ),
    ];
    // Search covers both tabs (summary and transcript), so it stays in the page menu.
    final wordsGroup = <PullDownMenuEntry>[
      // A locked conversation is refused to connectors until it is unlocked, so it is not offered.
      if (!conversation.discarded && !conversation.isLocked)
        PullDownMenuItem(
          title: l10n.askAboutConversation,
          iconWidget: const FaIcon(FontAwesomeIcons.message, size: 16),
          onTap: () {
            PlatformManager.instance.analytics.conversationThreeDotsMenuActionSelected(
              conversationId: conversation.id,
              action: 'ask_agent',
            );
            showAskAgentSheet(context, conversation);
          },
        ),
      PullDownMenuItem(
        title: l10n.search,
        iconWidget: const FaIcon(FontAwesomeIcons.magnifyingGlass, size: 16),
        onTap: () {
          trackConversationAction(ConversationActionAction.search, ConversationActionSurface.overflow);
          if (_isSearching) {
            _closeSearch();
          } else {
            setState(() => _isSearching = true);
            _searchFocusNode.requestFocus();
            PlatformManager.instance.analytics.conversationDetailSearchClicked(
              conversationId: provider.conversation.id,
            );
          }
          HapticFeedback.mediumImpact();
        },
      ),
      PullDownMenuItem(
        title: l10n.copyTranscript,
        iconWidget: const FaIcon(FontAwesomeIcons.copy, size: 16),
        onTap: () => _handleMenuSelection(context, 'copy_transcript', provider),
      ),
      if (provider.conversation.transcriptSegments.isNotEmpty)
        PullDownMenuItem(
          title: l10n.exportTranscript,
          iconWidget: const FaIcon(FontAwesomeIcons.fileLines, size: 16),
          onTap: _isSharing ? null : () => _handleMenuSelection(context, 'export_transcript', provider),
        ),
      if (!live)
        PullDownMenuItem(
          title: l10n.copySummary,
          iconWidget: const FaIcon(FontAwesomeIcons.clone, size: 16),
          onTap: () => _handleMenuSelection(context, 'copy_summary', provider),
        ),
      if (provider.conversation.hasAudio() && !live)
        PullDownMenuItem(
          title: l10n.shareAudio,
          iconWidget: const FaIcon(FontAwesomeIcons.share, size: 16),
          onTap: _isDownloadingAudio ? null : () => _handleMenuSelection(context, 'download_audio', provider),
        ),
    ];
    final developerGroup = <PullDownMenuEntry>[
      if (showDeveloperTools) ...[
        PullDownMenuItem(
          title: l10n.copyConversationId,
          iconWidget: const FaIcon(FontAwesomeIcons.clipboard, size: 16),
          onTap: () => _handleMenuSelection(context, 'copy_conversation_id', provider),
        ),
        PullDownMenuItem(
          title: l10n.testPrompt,
          iconWidget: const FaIcon(FontAwesomeIcons.commentDots, size: 16),
          onTap: () => _handleMenuSelection(context, 'test_prompt', provider),
        ),
      ],
    ];
    final deleteGroup = <PullDownMenuEntry>[
      // "Delete": the menu is already about this conversation.
      if (!live)
        PullDownMenuItem(
          title: l10n.delete,
          isDestructive: true,
          iconWidget: FaIcon(FontAwesomeIcons.trashCan, size: 16, color: OmiColors.danger),
          onTap: () => _handleMenuSelection(context, 'delete', provider),
        ),
    ];
    final groups = [summaryGroup, organizeGroup, wordsGroup, developerGroup, deleteGroup].where((g) => g.isNotEmpty);
    return [
      for (final (index, group) in groups.indexed) ...[if (index > 0) const PullDownMenuDivider.large(), ...group],
    ];
  }

  /// Ask about this conversation (#4515), from the bottom bar's Ask button or Ask Omi bar. Chat is a
  /// pushed page (D1).
  void _openAskOmi(ConversationDetailProvider provider) {
    trackConversationAction(ConversationActionAction.askOmi, ConversationActionSurface.detailBody);
    final convo = provider.conversation;
    openChatSheet(
      context,
      ChatPage(
        initialChatContext: ChatPageContext(type: 'conversation', id: convo.id, title: convo.structured.title),
      ),
    );
  }

  /// A v3 conversation still in progress (the account's v3 answer gates it, as on every tile-state
  /// reader). Its content is unfinished, so sharing, summary and editing actions wait for the end.
  bool _isLiveV3(ServerConversation conversation) =>
      (context.read<ConversationsV3Provider?>()?.v3 ?? false) &&
      conversation.v3?.tileState == ConversationTileState.live;

  /// Reliability experiment instant_live_text. The page shows the account's open conversation and this
  /// phone's capture feeds it: its listening recording is a source, or the server's device stamp says the
  /// latest speech came from this install.
  bool _showsOpenConversationThisPhoneFeeds(ServerConversation shown, CaptureProvider capture) {
    if (!mounted || _routeUid.isEmpty || _routeUid != SharedPreferencesUtil().uid) return false;
    if (_routeIdentityEpoch != AnalyticsManager.identityEpoch) return false;
    final current = _providerInitialized ? _detailProvider.conversationOrNull : widget.conversation;
    if (current == null ||
        (_providerInitialized && _detailProvider.detailAccessUnavailable) ||
        current.id != shown.id ||
        current.id != widget.conversation.id ||
        current.isLocked ||
        current.isHiddenFromDefaultList ||
        current.status != ConversationStatus.in_progress ||
        !_isLiveV3(current)) {
      return false;
    }
    final recordingId = capture.verifiedLiveServerRecordingId;
    if (recordingId != null && (current.v3?.recordingIds.contains(recordingId) ?? false)) return true;
    final live = context.read<ConversationsV3Provider?>()?.live;
    return LiveConversationEndButton.latestSpeechFromThisDevice(current,
        currentLiveId: live?.id, liveCaptureDeviceId: live?.v3?.captureDeviceId);
  }

  /// Reliability experiment instant_live_text: while this page shows the open conversation this phone
  /// feeds, the listening connection reports its transcript as on screen, exactly as the Listening page
  /// does. The server streams a batch-only session's audio for as long as that report stands, so the
  /// lines start the moment the page opens. Off, this page never reports.
  void _syncTranscriptOnScreenReport() {
    final capture = context.read<CaptureProvider?>();
    final want = ReliabilityExperiments.enabled('instant_live_text') &&
        capture != null &&
        _showsOpenConversationThisPhoneFeeds(widget.conversation, capture);
    if (want == _reportedTranscriptOnScreen) return;
    _reportedTranscriptOnScreen = want;
    // The report notifies listeners; never do that while this widget is building.
    scheduleMicrotask(
        want ? ListenClientState.instance.capturePageOpened : ListenClientState.instance.capturePageClosed);
  }

  /// Reliability experiment instant_live_text: the lines the server streamed to this phone's listening
  /// connection that the open conversation does not hold yet. Only where the phone shows no lines from
  /// its own recogniser (a session without the on-phone preview).
  Widget? _streamedLinesTail(ServerConversation conversation, CaptureProvider? capture, {Widget? whenEmpty}) {
    final startedAt = conversation.startedAt;
    if (!ReliabilityExperiments.enabled('instant_live_text') || capture == null || startedAt == null) return null;
    bool applies() => !capture.liveWordsShown && _showsOpenConversationThisPhoneFeeds(conversation, capture);
    if (!applies()) return null;
    final coverage = LivePreviewCoverage.forFinals(conversation.transcriptSegments, startedAt);
    return StreamedLinesTail(
      capture: capture,
      whenEmpty: whenEmpty,
      lines: () {
        final origin = capture.liveTranscriptStartedAt;
        if (origin == null || !applies()) return const [];
        DateTime at(double seconds) => origin.add(Duration(microseconds: (seconds * 1000000).round()));
        return coverage.excludeCovered([
          for (final segment in capture.segments)
            if (segment.text.trim().isNotEmpty && !at(segment.start).isBefore(startedAt))
              LivePreviewLine(
                  id: segment.id,
                  text: segment.text,
                  isFinal: true,
                  startedAt: at(segment.start),
                  endedAt: at(segment.end)),
        ]);
      },
    );
  }

  Widget? _livePreviewTail(ServerConversation conversation, CaptureProvider? capture, {Widget? whenEmpty}) {
    final preview = capture?.livePreview;
    final startedAt = conversation.startedAt;
    if (capture == null || preview == null || startedAt == null) return null;

    bool isVerified() {
      if (!mounted ||
          _routeUid.isEmpty ||
          _routeUid != SharedPreferencesUtil().uid ||
          _routeIdentityEpoch != AnalyticsManager.identityEpoch ||
          !identical(capture.livePreview, preview) ||
          !capture.liveWordsShown ||
          !preview.admitted ||
          !capture.pendantCaptureVerified) {
        return false;
      }
      final current = _providerInitialized ? _detailProvider.conversationOrNull : widget.conversation;
      if (current == null ||
          (_providerInitialized && _detailProvider.detailAccessUnavailable) ||
          current.startedAt != startedAt ||
          current.id != conversation.id ||
          current.id != widget.conversation.id ||
          current.isLocked ||
          current.isHiddenFromDefaultList) {
        return false;
      }
      if (current.status != ConversationStatus.in_progress || !_isLiveV3(current)) {
        // Reliability experiment live_words_cascade: a conversation that has ended keeps the live words
        // spoken inside its own time range until stored text replaces them (or they are five minutes
        // old), exactly as an open one does. Which words those are is decided by time alone, below.
        // Off: only the conversation in progress shows live words.
        return LivePreviewController.cascadeEnabled() &&
            current.v3 != null &&
            (context.read<ConversationsV3Provider?>()?.v3 ?? false);
      }
      final recordingId = capture.verifiedLiveServerRecordingId;
      if (recordingId != null && (current.v3?.recordingIds.contains(recordingId) ?? false)) return true;
      // Reliability experiment instant_live_text: a phone that uploads its speech as files never has its
      // listening recording among the sources. The server's device stamp on the open conversation says the
      // latest speech came from this install, which is the same fact.
      // Reliability experiment vendor_recognizer_on_opened_app shows its merged words by the same fact.
      if (!ReliabilityExperiments.enabled('instant_live_text') &&
          !ReliabilityExperiments.enabled('vendor_recognizer_on_opened_app')) {
        return false;
      }
      final live = context.read<ConversationsV3Provider?>()?.live;
      return LiveConversationEndButton.latestSpeechFromThisDevice(current,
          currentLiveId: live?.id, liveCaptureDeviceId: live?.v3?.captureDeviceId);
    }

    if (!isVerified()) return null;
    return LivePreviewTail.continuingTranscript(
      preview: preview,
      coverage: LivePreviewCoverage.forFinals(conversation.transcriptSegments, startedAt),
      whenEmpty: whenEmpty,
      lines: () {
        if (!isVerified()) return const [];
        final lines = LivePreviewController.cascadeEnabled()
            // Reliability experiment live_words_cascade: the live words of this conversation's own time
            // range, per word, whether it is open or has ended: from its start (never before the End that
            // preceded it) to the End that closed it. The tail then drops each word once a stored line
            // covers its moment, or after five minutes without one.
            ? preview.wordsFor(startedAt: startedAt, until: _liveWordsUntil())
            : [
                for (final line in preview.lines)
                  if (line.startedAt case final lineStart?)
                    if (!lineStart.isBefore(startedAt)) line,
              ];
        _recordLiveWordsHole(conversation, startedAt, lines);
        return lines;
      },
    );
  }

  /// Reliability experiment live_words_cascade: where this page's conversation stops owning live words.
  /// The End that closed it when the server has stamped one; for a conversation that ended by itself, a
  /// little after its last stored line; null while it is open (the live-words layer then stops it at an
  /// End pressed on this phone that the page has not heard of yet).
  DateTime? _liveWordsUntil() {
    final current = _providerInitialized ? _detailProvider.conversationOrNull : widget.conversation;
    if (current == null) return null;
    final closedBy = current.v3?.manualCutAt;
    if (closedBy != null) return closedBy;
    if (current.status == ConversationStatus.in_progress) return null;
    return current.finishedAt?.add(LivePreviewController.conversationLead);
  }

  // Reliability experiment vendor_recognizer_on_opened_app, step 4: a local record, numbers only, of
  // the stored lines, the live lines and the hole between them on this page, when its live lines are
  // first built and at most every 10 s after. Off, nothing is recorded.
  DateTime? _liveWordsHoleRecordedAt;

  void _recordLiveWordsHole(ServerConversation conversation, DateTime startedAt, List<LivePreviewLine> lines) {
    if (!ReliabilityExperiments.enabled('vendor_recognizer_on_opened_app')) return;
    final now = DateTime.now();
    final last = _liveWordsHoleRecordedAt;
    if (last != null && now.difference(last) < const Duration(seconds: 10)) return;
    _liveWordsHoleRecordedAt = now;
    LiveWordsLog.event('open_conversation_page', {
      'opened': last == null,
      ...LiveWordsHole.measure(stored: conversation.transcriptSegments, origin: startedAt, live: lines, now: now),
    });
  }

  /// Header actions: Star and Share as 44pt icon buttons, then one overflow holding the summary
  /// template, Rename, Move to Folder, Recordings and the rest, Delete last. Ask Omi is the bottom bar.
  /// While the conversation is still going, Share is hidden until it ends.
  Widget _buildHeaderActions(BuildContext context, ConversationDetailProvider provider) {
    final l10n = context.l10n;
    final starred = provider.conversation.starred;
    final live = _isLiveV3(provider.conversation);
    return Padding(
      padding: const EdgeInsets.only(right: OmiSpacing.xxs),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiIconButton.filled(
            key: const Key('conversation_star'),
            icon: _isTogglingStarred
                ? const OmiSpinner(size: OmiSpinnerSize.small)
                : FaIcon(starred ? FontAwesomeIcons.solidStar : FontAwesomeIcons.star, size: 16),
            label: starred ? l10n.unstarConversation : l10n.starConversation,
            color: starred ? Colors.amber : null,
            onPressed: _isTogglingStarred
                ? null
                : () {
                    trackConversationAction(
                      starred ? ConversationActionAction.unstar : ConversationActionAction.star,
                      ConversationActionSurface.topBar,
                    );
                    _toggleStarred(provider);
                  },
          ),
          // Also the share sheet's anchor (iPad needs one).
          if (!live)
            KeyedSubtree(
              key: _shareButtonKey,
              child: OmiIconButton.filled(
                key: const Key('conversation_share'),
                icon: _isSharing
                    ? const OmiSpinner(size: OmiSpinnerSize.small)
                    : const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16),
                label: l10n.share,
                onPressed: _isSharing
                    ? null
                    : () {
                        trackConversationAction(ConversationActionAction.share, ConversationActionSurface.topBar);
                        _shareConversation(provider);
                      },
              ),
            ),
          PullDownButton(
            itemBuilder: (context) => _menuItems(context, provider),
            buttonBuilder: (context, showMenu) => OmiIconButton.filled(
              key: const Key('conversation_more'),
              icon: const FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16),
              label: l10n.moreOptions,
              onPressed: () {
                HapticFeedback.mediumImpact();
                PlatformManager.instance.analytics.conversationThreeDotsMenuOpened(
                  conversationId: provider.conversation.id,
                );
                showMenu();
              },
            ),
          ),
        ],
      ),
    );
  }

  void _onSearchChanged(String value) {
    setState(() {
      _searchQuery = value;
      _updateSearchResults();
      if (value.isNotEmpty) {
        final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
        PlatformManager.instance.analytics.conversationDetailSearchQueryEntered(
          conversationId: provider.conversation.id,
          query: value,
          resultsCount: _totalSearchResults,
          activeTab: _getTabTitle(context, selectedTab),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // Empty shell on first build (before initState's setCachedConversation
    // post-frame); after init, an unresolved conversation pops the route.
    final detailProvider = context.watch<ConversationDetailProvider>();
    final conversation = detailProvider.conversationOrNull;
    context.select<CaptureProvider?, (LivePreviewController?, bool, bool, String?)>((capture) => (
          capture?.livePreview,
          capture?.liveWordsShown ?? false,
          capture?.pendantCaptureVerified ?? false,
          capture?.verifiedLiveServerRecordingId,
        ));
    final capture = context.read<CaptureProvider?>();
    context.select<ConversationsV3Provider?, bool>((provider) => provider?.v3 ?? false);
    if (ReliabilityExperiments.enabled('instant_live_text') ||
        ReliabilityExperiments.enabled('vendor_recognizer_on_opened_app')) {
      // The device stamp arrives on the live read; rebuild when it does.
      context.select<ConversationsV3Provider?, (String?, String?)>(
          (provider) => (provider?.live?.id, provider?.live?.v3?.captureDeviceId));
    }
    _syncLiveSummaryTimer();
    _syncTranscriptOnScreenReport();
    if (!_providerInitialized) {
      final preview = selectedTab == ConversationTab.transcript ? _livePreviewTail(widget.conversation, capture) : null;
      return Scaffold(
        backgroundColor: OmiColors.surface0,
        body: preview == null
            ? null
            : SafeArea(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                  child: preview,
                ),
              ),
      );
    }
    if (conversation == null) {
      if (_providerInitialized) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (Navigator.of(context).canPop()) {
            Navigator.of(context).pop();
          }
        });
      }
      return const Scaffold();
    }

    // The bottom bar (and its backdrop) shows once there is something to play or ask about, and always
    // on a conversation still in progress, whose bar carries End before its transcript arrives.
    final hasBar = conversation.transcriptSegments.isNotEmpty ||
        conversation.photos.isNotEmpty ||
        conversation.externalIntegration != null ||
        (context.select<ConversationsV3Provider?, bool>((p) => p?.v3 ?? false) &&
            conversation.v3?.tileState == ConversationTileState.live);

    return MessageListener<ConversationDetailProvider>(
      showError: (error) {
        switch (error) {
          case 'REPROCESS_FAILED':
            // The redesigned Summary tab explains the failure in place, with its own actions.
            if (SummaryGenerationV2Gate.isEnabled) break;
            // The provider is shared: a reprocess started on another conversation can fail after
            // the reader opened this one. Report only this page's own failure, and retry only it.
            final failedId = detailProvider.lastFailedReprocessConversationId;
            if (failedId == null || failedId != detailProvider.conversationOrNull?.id) break;
            final appId = detailProvider.lastFailedReprocessAppId;
            OmiFeedback.error(
              context,
              context.l10n.errorProcessingConversation,
              actionLabel: context.l10n.tryAgain,
              onAction: () {
                if (detailProvider.conversationOrNull?.id == failedId) {
                  // The failure card explaining the retry lives on the Summary tab.
                  _openSummaryTab();
                  detailProvider.reprocessConversation(appId: appId);
                }
              },
            );
          case 'SEGMENT_EDIT_FAILED':
          case 'SUMMARY_EDIT_FAILED':
            OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
        }
      },
      showInfo: (info) {
        switch (info) {
          case 'REPROCESS_SUCCESS':
            if (detailProvider.reprocessedConversationId == detailProvider.conversationOrNull?.id) {
              OmiFeedback.confirm(context, context.l10n.conversationReprocessed);
            }
          case 'REPROCESS_TRANSCRIPTION_PENDING':
            // The redesigned Summary tab explains this in place.
            if (SummaryGenerationV2Gate.isEnabled) break;
            final open = detailProvider.conversationOrNull;
            final failedId = detailProvider.lastFailedReprocessConversationId;
            if (open == null || failedId == null || failedId != open.id) break;
            // The legacy Summary tab's empty state already shows the same notice in place.
            final noticeShown = selectedTab == ConversationTab.summary &&
                detailProvider.getDisplayedSummarySelection().kind == ConversationSummaryKind.empty &&
                summaryRetrySlotApplies(open);
            if (noticeShown) break;
            OmiFeedback.info(context, context.l10n.summaryTranscriptionPendingBody);
        }
      },
      child: Scaffold(
        key: scaffoldKey,
        extendBody: true,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          leading: const Center(child: OmiBackButton.circled()),
          // No title: the tab bar below already names the active view, so a
          // header label only crowds the row with the back button and actions.
          // _getTabTitle still backs the `active_tab` search analytics property.
          titleSpacing: 0,
          actions: [_buildHeaderActions(context, detailProvider)],
        ),
        // Toasts float above the pinned Ask Omi bar instead of covering it.
        body: OmiFeedbackClearance(
          bottom: hasBar ? detailToastClearance(MediaQuery.viewPaddingOf(context).bottom) : 0,
          child: Stack(
            children: [
              GestureDetector(
                excludeFromSemantics: true,
                behavior: HitTestBehavior.translucent,
                // Tapping content closes an empty search. There is deliberately no horizontal
                // gesture here: a sideways swipe moves between the tabs, never to another
                // conversation (D2), and the iOS edge swipe always goes back.
                onTap: _closeSearchIfEmpty,
                child: Column(
                  children: [
                    // Title and facts, shared by both tabs (#17297), then the tab row (v3).
                    ConversationDetailHeader(onOpenRecordings: _openRecordings),
                    if (conversation.processingDeferred)
                      const Padding(padding: EdgeInsets.all(OmiSpacing.xs), child: ProcessingDeferredMarker()),
                    ConversationDetailTabs(controller: _controller!, onTap: _onDetailTabTap),
                    ConversationActivityStrip(summaryTabVisible: selectedTab == ConversationTab.summary),
                    Expanded(
                      // Each tab owns the page's side margin, so a section can scroll edge to edge
                      // (the Summary tab's screenshot strip) instead of clipping at the margin.
                      child: NotificationListener<ScrollNotification>(
                        onNotification: _onDetailTabScroll,
                        child: TabBarView(
                          controller: _controller,
                          children: [
                            SummaryTab(
                              liveSummaryOpen: _summaryOpen,
                              liveSummaryTick: _liveSummaryTick,
                              claimLiveSummaryOpen: _claimSummaryOpen,
                              isLiveSummaryVisible: _summaryTabIsVisible,
                              liveSummaryInterval: _liveSummaryIntervalForDispatch,
                              onOpenSource: (id) {
                                final segments = detailProvider.conversation.transcriptSegments;
                                final segment = segments.where((segment) => segment.id == id).firstOrNull;
                                if (segment == null) return;
                                _hasExplicitTabSelection = true;
                                setState(() => selectedTab = ConversationTab.transcript);
                                _controller!.animateTo(_transcriptTabIndex);
                                _playbackController.updateSegments(segments);
                                _playbackController.seek(segment.start, strict: true);
                              },
                              reviewEnabled: !widget.isFromOnboarding &&
                                  widget.initialSeekStart == null &&
                                  selectedTab == ConversationTab.summary &&
                                  !_controller!.indexIsChanging &&
                                  !_isSearching &&
                                  !_isSharing &&
                                  !_isDownloadingAudio &&
                                  !_reviewInterrupted,
                              searchQuery: _searchQuery,
                              currentResultIndex: getCurrentResultIndexForHighlighting(),
                              summarySearchResultOffset: _summaryContentSearchResults,
                              onTapWhenSearchEmpty: _closeSearchIfEmpty,
                              onShowActionItemInTranscript: _showActionItemInTranscript,
                            ),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                              child: TranscriptWidgets(
                                searchQuery: _searchQuery,
                                currentResultIndex: getCurrentResultIndexForHighlighting(),
                                onTapWhenSearchEmpty: _closeSearchIfEmpty,
                                onSegmentTap: (segment) async {
                                  if (selectedTab != ConversationTab.transcript) {
                                    setState(() {
                                      selectedTab = ConversationTab.transcript;
                                    });
                                    _controller!.animateTo(_transcriptTabIndex);
                                  }

                                  // Seek to segment start; playback keeps running past the segment end.
                                  if (_seekToSegmentCallback != null) {
                                    await _seekToSegmentCallback!(segment.start, segment.end);
                                  }
                                },
                                playbackController: _playbackController,
                                livePreviewTail: (row, whenEmpty) =>
                                    _livePreviewTail(row, capture, whenEmpty: whenEmpty) ??
                                    _streamedLinesTail(row, capture, whenEmpty: whenEmpty),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Floating bottom bar — hidden while keyboard is up (e.g. inline summary edit). The page
              // colour fades in behind it so text never runs under the bar.
              if (MediaQuery.of(context).viewInsets.bottom == 0 && hasBar)
                _DetailBarBackdrop(
                    barBottom: detailFloatingBarBottom(MediaQuery.viewPaddingOf(context).bottom),
                    soft: ExperimentalDesign.of(context)),
              if (MediaQuery.of(context).viewInsets.bottom == 0)
                Positioned(
                  // Stable key so the body Stack's collection-`if` diff matches
                  // by identity, not by slot+type. Without it the surviving
                  // search-overlay Positioned below was being reused into this
                  // slot when the keyboard rose, tearing down the search
                  // TextField subtree and dropping the IME mid-frame.
                  key: const ValueKey('detail_floating_bottom_bar'),
                  bottom: detailFloatingBarBottom(MediaQuery.viewPaddingOf(context).bottom),
                  left: 0,
                  right: 0,
                  child: ConversationBottomBar(
                    onAudioInteraction: () {
                      if (mounted && !_reviewInterrupted) setState(() => _reviewInterrupted = true);
                    },
                    mode: ConversationBottomBarMode.detail,
                    onAskOmi: () => _openAskOmi(detailProvider),
                    selectedTab: selectedTab,
                    conversation: conversation,
                    hasSegments: hasBar,
                    playbackController: _playbackController,
                    onSeekFunctionReady: (seekFunction) {
                      WidgetsBinding.instance.addPostFrameCallback((_) {
                        if (mounted) {
                          setState(() {
                            _seekToSegmentCallback = seekFunction;
                          });
                          _maybePlayInitialSeek();
                        }
                      });
                    },
                    onTabSelected: (tab) {
                      final index = _indexForTab(tab);
                      if (index < _controller!.length) {
                        _onDetailTabTap(index);
                        _controller!.animateTo(index);
                      }
                    },
                    onLiveEndSuppressionChanged: (suppressed) {
                      if (!mounted) return;
                      _liveEndRequested = suppressed;
                      _summaryOpenPending = false;
                      _syncLiveSummaryTimer();
                      if (suppressed) {
                        // Start at the tap: the page knows its conversation before the server answers.
                        context
                            .read<ConversationsV3Provider?>()
                            ?.awaitSummaryAfterEnd(_detailProvider.conversationOrNull?.id);
                      }
                    },
                    onStopPressed: () {
                      // Empty since we don't show the stop button in detail mode
                    },
                  ),
                ),

              // Search bar over the content
              if (_isSearching)
                Positioned(
                  // Stable key — same reason as the floating bottom bar above.
                  // Without it the keyboard pop-up flickered closed because
                  // the body Stack's diff was reusing this Positioned's
                  // element into the bar's slot and remounting the TextField.
                  key: const ValueKey('detail_search_overlay'),
                  top: 0,
                  left: 0,
                  right: 0,
                  child: DetailSearchBar(
                    controller: _searchController,
                    focusNode: _searchFocusNode,
                    query: _searchQuery,
                    currentIndex: _currentSearchIndex,
                    totalResults: _totalSearchResults,
                    onChanged: _onSearchChanged,
                    onPrevious: () => _navigateSearch(false),
                    onNext: () => _navigateSearch(true),
                    onCancel: _closeSearch,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Solid page colour from the screen edge up through the floating bar, fading out above it. Paint
/// only; a [Stack] child placed before the bar.
class _DetailBarBackdrop extends StatelessWidget {
  const _DetailBarBackdrop({required this.barBottom, this.soft = false});

  /// Under a glass bar: the text fades out towards the bar over a longer run and is never fully
  /// covered, so the bar has something behind it and no sharp line of text at its edge.
  final bool soft;

  /// Distance from the screen edge to the bar's bottom.
  final double barBottom;

  static const double _barHeight = detailFloatingBarHeight;
  static const double _fade = 28;

  @override
  Widget build(BuildContext context) {
    final fade = soft ? 72.0 : _fade;
    final height = barBottom + _barHeight + fade;
    final page = OmiColors.surface0;
    return Positioned(
      key: const ValueKey('detail_bar_backdrop'),
      left: 0,
      right: 0,
      bottom: 0,
      height: height,
      child: IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0, fade / height, 1],
              colors: soft
                  ? [page.withValues(alpha: 0), page.withValues(alpha: 0.7), page.withValues(alpha: 0.9)]
                  : [page.withValues(alpha: 0), page, page],
            ),
          ),
        ),
      ),
    );
  }
}
