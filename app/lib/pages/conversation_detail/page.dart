import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/messages.dart' show ChatPageContext;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/pages/settings/integrations_page.dart' show IntegrationApp, IntegrationsPage;
import 'package:omi/services/audio_download_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_sheet.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'conversation_detail_provider.dart';
import 'conversation_summary_selection.dart';
import 'share.dart';
import 'test_prompts.dart';
import 'widgets/audio_download_progress_sheet.dart';
import 'capture_group_separation.dart';
import 'widgets/calendar_event_sheets.dart';
import 'widgets/capture_recordings.dart';
import 'widgets/conversation_detail_header.dart';
import 'widgets/conversation_tasks_tab.dart';
import 'widgets/detail_search_bar.dart';
import 'widgets/summary_tab.dart';
import 'widgets/share_to_contacts_sheet.dart';
import 'widgets/transcript_tab.dart';

/// Offset of the floating bottom bar from the bottom of the screen.
///
/// 32pt is the bar's resting position and already clears the iPhone home
/// indicator. Android 16 draws a 3-button navigation bar up to 48dp tall over
/// this edge-to-edge body, which covered the lower part of the bar's buttons,
/// so the bar never sits lower than the inset the window reports.
double detailFloatingBarBottom(double bottomSystemInset) => math.max(32, bottomSystemInset);

/// Chooses the first useful detail tab for a conversation.
///
/// A caller-supplied tab is authoritative: search deep links use it to
/// preserve the user's context. When no tab was requested, a completed
/// conversation with transcript text but no generated summary opens on the
/// transcript so retained fragment data is immediately visible.
int conversationDetailInitialTabIndex(ServerConversation conversation, {int? requestedTabIndex}) {
  if (requestedTabIndex != null) return requestedTabIndex;
  if (conversation.status != ConversationStatus.completed) return 1;

  final hasTranscript = conversation.transcriptSegments.any((segment) => segment.text.trim().isNotEmpty);
  final hasSummary = ConversationSummarySelection.select(conversation).kind != ConversationSummaryKind.empty;
  return hasTranscript && !hasSummary ? 0 : 1;
}

/// Tab indices of the detail page. The Tasks tab exists only while the conversation has tasks.
const int _transcriptTabIndex = 0;
const int _summaryTabIndex = 1;
const int _tasksTabIndex = 2;

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
  final int? initialTabIndex;

  /// When set (e.g. from search match snippet), open transcript and play this moment.
  final double? initialSeekStart;
  final double? initialSeekEnd;

  const ConversationDetailPage({
    super.key,
    this.isFromOnboarding = false,
    required this.conversation,
    this.openShareToContactsOnLoad = false,
    this.initialTabIndex,
    this.initialSeekStart,
    this.initialSeekEnd,
  });

  @override
  State<ConversationDetailPage> createState() => ConversationDetailPageState();
}

class ConversationDetailPageState extends State<ConversationDetailPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  final GlobalKey _shareButtonKey = GlobalKey();
  TabController? _controller;
  ConversationTab selectedTab = ConversationTab.summary;

  // Callback to seek audio to transcript segment (start, end) in wall seconds
  Future<void> Function(double start, double end)? _seekToSegmentCallback;
  bool _isSharing = false;
  bool _reviewInterrupted = false;
  bool _isTogglingStarred = false;
  bool _isDownloadingAudio = false;
  bool _providerInitialized = false;
  bool _didInitialSeek = false;
  bool _hasExplicitTabSelection = false;
  bool _resultViewedRecorded = false;

  // Search functionality
  bool _isSearching = false;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();
  int _currentSearchIndex = 0;
  int _totalSearchResults = 0;
  final List<(Timer, Completer<void>)> _ownedDelays = [];
  final _separation = CaptureGroupSeparationController();

  void _updateSearchResults() {
    if (_searchQuery.isEmpty) {
      _totalSearchResults = 0;
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
    if (selectedTab == ConversationTab.transcript) {
      for (var segment in provider.conversation.transcriptSegments) {
        count += countIn(segment.text.toLowerCase());
      }
    } else if (selectedTab == ConversationTab.summary) {
      final summarySelection = provider.getSummarySelection();
      if (summarySelection.content.isNotEmpty) {
        count += countIn(summarySelection.content.decodeString.toLowerCase());
      }
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

  static ConversationTab _tabForIndex(int index) => switch (index) {
        _transcriptTabIndex => ConversationTab.transcript,
        _tasksTabIndex => ConversationTab.actionItems,
        _ => ConversationTab.summary,
      };

  static int _indexForTab(ConversationTab tab) => switch (tab) {
        ConversationTab.transcript => _transcriptTabIndex,
        ConversationTab.summary => _summaryTabIndex,
        ConversationTab.actionItems => _tasksTabIndex,
      };

  void _createTabController({required int length, required int initialIndex}) {
    _controller = TabController(length: length, vsync: this, initialIndex: initialIndex.clamp(0, length - 1));
    _controller!.addListener(_onTabChanged);
  }

  /// The Tasks tab exists only while there are tasks, so a swipe never lands on a tab the
  /// bottom bar has no button for. Rebuilds the controller when that changes.
  void _syncTabCount(bool hasTasks) {
    final length = hasTasks ? 3 : 2;
    final old = _controller;
    if (old == null || old.length == length) return;
    old.removeListener(_onTabChanged);
    _createTabController(length: length, initialIndex: old.index);
    selectedTab = _tabForIndex(_controller!.index);
    WidgetsBinding.instance.addPostFrameCallback((_) => old.dispose());
  }

  void _onTabChanged() {
    final tab = _tabForIndex(_controller!.index);
    if (tab == selectedTab) return;
    setState(() {
      selectedTab = tab;
      PlatformManager.instance.analytics.conversationDetailTabChanged(switch (tab) {
        ConversationTab.transcript => 'Transcript',
        ConversationTab.summary => 'Summary',
        ConversationTab.actionItems => 'Action Items',
      });
      if (_searchQuery.isNotEmpty) _updateSearchResults();
    });
  }

  @override
  void initState() {
    super.initState();

    // The supplied conversation can be a list projection whose app results
    // are hydrated after the first frame. Start on Summary, then select the
    // transcript only once the final summary state is known.
    final initialTabIndex = widget.initialTabIndex ?? _summaryTabIndex;
    _createTabController(length: 3, initialIndex: initialTabIndex);
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
      if (provider.conversation.appResults.isEmpty) {
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
        }
      } else {
        _selectInitialTabIfNeeded(provider.conversation);
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
      ConversationTab.actionItems =>
        conversation.structured.actionItems.any((item) => !item.deleted && item.description.trim().isNotEmpty),
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
    if (!mounted ||
        widget.initialTabIndex != null ||
        _hasExplicitTabSelection ||
        _controller?.index != _summaryTabIndex) {
      return;
    }
    final index = conversationDetailInitialTabIndex(conversation);
    if (index == _summaryTabIndex) return;
    setState(() {
      selectedTab = ConversationTab.transcript;
    });
    _controller?.animateTo(index);
  }

  @override
  void dispose() {
    _cancelOwnedTimers();
    _separation.dispose();
    _controller?.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
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
      case ConversationTab.actionItems:
        return context.l10n.actionItemsTab;
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
          initialTabIndex: _controller?.index,
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
    return _separation.separate(recording.id, reload: () async {
      await detail.refreshConversation();
      await (list.hasActiveSearch ? list.searchConversations(list.previousQuery) : list.forceRefreshConversations());
    });
  }

  static const _overflowActions = {
    'copy_transcript': ConversationActionAction.copyTranscript,
    'copy_summary': ConversationActionAction.copySummary,
    'download_audio': ConversationActionAction.shareAudio,
    'test_prompt': ConversationActionAction.testPrompt,
    'reprocess': ConversationActionAction.reprocess,
    'link_event': ConversationActionAction.linkEvent,
    'copy_conversation_id': ConversationActionAction.copyConversationId,
    'rename': ConversationActionAction.rename,
    'move_to_folder': ConversationActionAction.moveFolder,
    'recordings': ConversationActionAction.recordingsOpen,
    'delete': ConversationActionAction.delete,
  };

  void _handleMenuSelection(BuildContext context, String value, ConversationDetailProvider provider) async {
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
      case 'copy_summary':
        final conversation = provider.conversation;
        _copyContent(context, ConversationSummarySelection.select(conversation).content, context.l10n.summary);
        break;
      case 'download_audio':
        await _downloadAudio(context, provider);
        break;
      case 'test_prompt':
        routeToPage(context, TestPromptsPage(conversation: provider.conversation));
        break;
      case 'reprocess':
        if (!provider.loadingReprocessConversation && !provider.loadingReprocessTranscription) {
          await provider.reprocessConversation();
        }
        break;
      case 'reprocess_transcription':
        if (!provider.loadingReprocessConversation && !provider.loadingReprocessTranscription) {
          await provider.reprocessTranscription();
        }
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
    } finally {
      if (mounted) setState(() => _isTogglingStarred = false);
    }
  }

  /// Shares the conversation's link. A private conversation is made public only after the reader
  /// agrees ("Anyone with the link can view"), and goes back to private if the share sheet reports
  /// that it was dismissed without sharing.
  Future<void> _shareConversation(ConversationDetailProvider provider) async {
    HapticFeedback.mediumImpact();
    final conversation = provider.conversation;
    final wasPrivate = conversation.visibility != ConversationVisibility.shared;
    if (wasPrivate) {
      final confirmed = await showOmiConfirm(
        context,
        title: context.l10n.shareConversationQuestion,
        message: context.l10n.anyoneWithLinkCanView,
        confirmLabel: context.l10n.share,
      );
      if (!confirmed || !mounted) return;
    }

    setState(() => _isSharing = true);
    try {
      if (wasPrivate) {
        final shared = await setConversationVisibility(conversation.id);
        if (!mounted) return;
        if (!shared) {
          OmiFeedback.error(context, context.l10n.conversationUrlNotShared);
          return;
        }
        provider.updateVisibilityLocally(ConversationVisibility.shared);
      }
      PlatformManager.instance.analytics.conversationShared(conversation: conversation, shareMethod: 'url_share');
      final origin = shareSheetOrigin(_shareButtonKey);
      // The sheet is up once the call is made; the button stops spinning while it is shown.
      final result = shareConversationLink(conversation, sharePositionOrigin: origin);
      await _delay(const Duration(milliseconds: 150));
      if (mounted) setState(() => _isSharing = false);
      final outcome = await result;
      if (wasPrivate && outcome.status == ShareResultStatus.dismissed) {
        final reverted = await setConversationVisibility(
          conversation.id,
          visibility: ConversationVisibility.private_.value,
        );
        if (reverted && mounted) provider.updateVisibilityLocally(ConversationVisibility.private_);
      }
    } catch (e) {
      Logger.debug('Failed to share conversation: $e');
    } finally {
      if (mounted && _isSharing) setState(() => _isSharing = false);
    }
  }

  List<PullDownMenuEntry> _menuItems(BuildContext context, ConversationDetailProvider provider) {
    final l10n = context.l10n;
    final showDeveloperTools = conversationDetailShowsDeveloperTools();
    final conversation = provider.conversation;
    final hasRecordings = CaptureGroupPresentation.recordings(conversation).isNotEmpty;
    return [
      // The conversation's own actions first; Star and Share live in the top bar; Delete stays last.
      if (!conversation.discarded)
        PullDownMenuItem(
          title: l10n.renameConversation,
          iconWidget: const FaIcon(FontAwesomeIcons.pen, size: 16),
          onTap: () => _handleMenuSelection(context, 'rename', provider),
        ),
      PullDownMenuItem(
        title: l10n.moveToFolder,
        iconWidget: const FaIcon(FontAwesomeIcons.folder, size: 16),
        onTap: () => _handleMenuSelection(context, 'move_to_folder', provider),
      ),
      if (hasRecordings)
        PullDownMenuItem(
          title: l10n.recordings,
          iconWidget: const FaIcon(FontAwesomeIcons.layerGroup, size: 16),
          onTap: () => _handleMenuSelection(context, 'recordings', provider),
        ),
      const PullDownMenuDivider.large(),
      if (selectedTab != ConversationTab.actionItems)
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
      PullDownMenuItem(
        title: l10n.copySummary,
        iconWidget: const FaIcon(FontAwesomeIcons.clone, size: 16),
        onTap: () => _handleMenuSelection(context, 'copy_summary', provider),
      ),
      if (provider.conversation.hasAudio())
        PullDownMenuItem(
          title: l10n.shareAudio,
          iconWidget: const FaIcon(FontAwesomeIcons.share, size: 16),
          onTap: _isDownloadingAudio ? null : () => _handleMenuSelection(context, 'download_audio', provider),
        ),
      if (provider.conversation.hasAudio())
        PullDownMenuItem(
          title: l10n.reprocessTranscription,
          iconWidget: const FaIcon(FontAwesomeIcons.microphone, size: 16),
          onTap: () => _handleMenuSelection(context, 'reprocess_transcription', provider),
        ),
      if (provider.conversation.calendarEvent == null)
        PullDownMenuItem(
          title: l10n.linkEvent,
          iconWidget: ClipRRect(
            borderRadius: const BorderRadius.all(Radius.circular(4)),
            child: Image.asset('assets/integration_app_logos/google-calendar.png', width: 17, height: 17),
          ),
          onTap: () => _handleMenuSelection(context, 'link_event', provider),
        ),
      if (!provider.conversation.discarded)
        PullDownMenuItem(
          title: l10n.reprocessConversation,
          iconWidget: const FaIcon(FontAwesomeIcons.arrowsRotate, size: 16),
          onTap: () => _handleMenuSelection(context, 'reprocess', provider),
        ),
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
      PullDownMenuItem(
        title: l10n.deleteConversation,
        isDestructive: true,
        iconWidget: const FaIcon(FontAwesomeIcons.trashCan, size: 16, color: OmiColors.danger),
        onTap: () => _handleMenuSelection(context, 'delete', provider),
      ),
    ];
  }

  /// Header actions (David, 2026-09-24): Ask Omi as the primary, then Star and Share as 44pt icon
  /// buttons, then one overflow holding Rename, Move to Folder, Recordings and the rest, Delete last.
  Widget _buildHeaderActions(BuildContext context, ConversationDetailProvider provider) {
    final l10n = context.l10n;
    final starred = provider.conversation.starred;
    return Padding(
      padding: const EdgeInsets.only(right: OmiSpacing.xxs),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Ask about this conversation (#4515). Chat is a pushed page (D1). Same fill and colours as the
          // Star and Share circles beside it (David, 2026-09-24): one calm row, no white primary.
          OmiButton.toolbar(
            key: const Key('conversation_ask_omi'),
            label: l10n.askOmi,
            // The bottom nav's two-bubbles glyph (FontAwesome comments, regular), so Ask Omi reads as
            // the same place as the Chat tab.
            leading: const FaIcon(kAskOmiGlyph),
            size: OmiButtonSize.compact,
            onPressed: () {
              HapticFeedback.mediumImpact();
              trackConversationAction(ConversationActionAction.askOmi, ConversationActionSurface.topBar);
              final convo = provider.conversation;
              routeToPage(
                context,
                ChatPage(
                  initialChatContext:
                      ChatPageContext(type: 'conversation', id: convo.id, title: convo.structured.title),
                ),
              );
            },
          ),
          const SizedBox(width: OmiSpacing.xxs),
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

    final hasTasks = conversation.structured.actionItems.any((item) => !item.deleted);
    if (_providerInitialized) _syncTabCount(hasTasks);

    return MessageListener<ConversationDetailProvider>(
      showError: (error) {
        if (error == 'REPROCESS_FAILED') {
          OmiFeedback.error(context, context.l10n.errorProcessingConversation);
        } else if (error == 'REPROCESS_TRANSCRIPTION_FAILED') {
          OmiFeedback.error(context, context.l10n.errorReprocessingTranscription);
        } else if (error == 'REPROCESS_TRANSCRIPTION_NO_AUDIO') {
          OmiFeedback.error(context, context.l10n.errorNoStoredAudio);
        }
      },
      showInfo: (info) {},
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
        body: Stack(
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
                  // Title and facts, shared by every tab (#17297).
                  ConversationDetailHeader(onOpenRecordings: _openRecordings),
                  Expanded(
                      child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                    child: TabBarView(
                      controller: _controller,
                      children: [
                        TranscriptWidgets(
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

                            // Seek to segment using callback (start + end for bounded play)
                            if (_seekToSegmentCallback != null) {
                              await _seekToSegmentCallback!(segment.start, segment.end);
                              HapticFeedback.lightImpact();
                            }
                          },
                        ),
                        SummaryTab(
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
                          onTapWhenSearchEmpty: _closeSearchIfEmpty,
                        ),
                        if (_controller!.length > _tasksTabIndex) const ActionItemsTab(),
                      ],
                    ),
                  )),
                ],
              ),
            ),

            // Floating bottom bar — hidden while keyboard is up (e.g. inline summary edit)
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
                  selectedTab: selectedTab,
                  conversation: conversation,
                  hasSegments: conversation.transcriptSegments.isNotEmpty ||
                      conversation.photos.isNotEmpty ||
                      conversation.externalIntegration != null,
                  hasActionItems: hasTasks,
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
                    _hasExplicitTabSelection = true;
                    final index = _indexForTab(tab);
                    if (index < _controller!.length) _controller!.animateTo(index);
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
    );
  }
}
