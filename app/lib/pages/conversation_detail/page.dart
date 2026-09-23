import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shimmer/shimmer.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/messages.dart' show ChatPageContext;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/pages/settings/integrations_page.dart' show IntegrationApp, IntegrationsPage;
import 'package:omi/services/audio_download_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/share_sheet.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'conversation_detail_provider.dart';
import 'conversation_summary_selection.dart';
import 'share.dart';
import 'test_prompts.dart';
import 'widgets/audio_download_progress_sheet.dart';
import 'widgets/edit_segment_sheet.dart';
import 'widgets/name_speaker_sheet.dart';
import 'widgets/summary_tab.dart';
import 'widgets/share_to_contacts_sheet.dart';
import 'widgets/speaker_summary_action.dart';

// import 'share.dart';
// import 'package:omi/pages/settings/developer.dart';
// import 'package:omi/backend/http/webhooks.dart';

/// Offset of the floating bottom bar from the bottom of the screen.
///
/// 32pt is the bar's resting position and already clears the iPhone home
/// indicator. Android 16 draws a 3-button navigation bar up to 48dp tall over
/// this edge-to-edge body, which covered the lower part of the bar's buttons,
/// so the bar never sits lower than the inset the window reports.
double detailFloatingBarBottom(double bottomSystemInset) => math.max(32, bottomSystemInset);

/// Chooses the first useful detail tab for a conversation.
///
/// A caller-supplied tab is authoritative: search deep links and adjacent
/// conversation navigation use it to preserve the user's context. When no
/// tab was requested, a completed conversation with transcript text but no
/// generated summary opens on the transcript so retained fragment data is
/// immediately visible.
int conversationDetailInitialTabIndex(ServerConversation conversation, {int? requestedTabIndex}) {
  if (requestedTabIndex != null) return requestedTabIndex;
  if (conversation.status != ConversationStatus.completed) return 1;

  final hasTranscript = conversation.transcriptSegments.any((segment) => segment.text.trim().isNotEmpty);
  final hasSummary = ConversationSummarySelection.select(conversation).kind != ConversationSummaryKind.empty;
  return hasTranscript && !hasSummary ? 0 : 1;
}

class ConversationDetailPage extends StatefulWidget {
  final ServerConversation conversation;
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
  List<int> _searchResultPositions = []; // Track positions of search results
  final List<(Timer, Completer<void>)> _ownedDelays = [];

  // TODO: use later for onboarding transcript segment edits
  // late AnimationController _animationController;
  // late Animation<double> _opacityAnimation;

  void _updateSearchResults() {
    if (_searchQuery.isEmpty) {
      _totalSearchResults = 0;
      _currentSearchIndex = 0;
      _searchResultPositions.clear();
      return;
    }

    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    int count = 0;
    _searchResultPositions.clear();

    // Count matches in transcript
    if (selectedTab == ConversationTab.transcript) {
      for (var segment in provider.conversation.transcriptSegments) {
        final text = segment.text.toLowerCase();
        final query = _searchQuery.toLowerCase();
        int index = 0;
        while ((index = text.indexOf(query, index)) != -1) {
          _searchResultPositions.add(count);
          count++;
          index += query.length;
        }
      }
    } else if (selectedTab == ConversationTab.summary) {
      // Count matches in app summaries
      final summarySelection = provider.getSummarySelection();
      if (summarySelection.content.isNotEmpty) {
        final appContent = summarySelection.content.decodeString.toLowerCase();
        final query = _searchQuery.toLowerCase();
        int index = 0;
        while ((index = appContent.indexOf(query, index)) != -1) {
          _searchResultPositions.add(count);
          count++;
          index += query.length;
        }
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

  @override
  void initState() {
    super.initState();

    // The supplied conversation can be a list projection whose app results
    // are hydrated after the first frame. Start on Summary, then select the
    // transcript only once the final summary state is known.
    final initialTabIndex = widget.initialTabIndex ?? 1;
    _controller = TabController(length: 3, vsync: this, initialIndex: initialTabIndex);
    selectedTab = switch (initialTabIndex) {
      0 => ConversationTab.transcript,
      2 => ConversationTab.actionItems,
      _ => ConversationTab.summary,
    };
    _controller!.addListener(() {
      setState(() {
        String? tabName;
        switch (_controller!.index) {
          case 0:
            selectedTab = ConversationTab.transcript;
            tabName = 'Transcript';
            break;
          case 1:
            selectedTab = ConversationTab.summary;
            tabName = 'Summary';
            break;
          case 2:
            selectedTab = ConversationTab.actionItems;
            tabName = 'Action Items';
            break;
          default:
            Logger.debug('Invalid tab index: ${_controller!.index}');
            selectedTab = ConversationTab.summary;
        }
        if (tabName != null) {
          PlatformManager.instance.analytics.conversationDetailTabChanged(tabName);
        }
        if (_searchQuery.isNotEmpty) {
          _updateSearchResults();
        }
      });
    });

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
        final (date, index) = result;
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
    // _animationController = AnimationController(
    //   vsync: this,
    //   duration: const Duration(seconds: 60),
    // )..repeat(reverse: true);
    //
    // _opacityAnimation = Tween<double>(begin: 1.0, end: 0.5).animate(_animationController);
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
    if (!mounted || widget.initialTabIndex != null || _hasExplicitTabSelection || _controller?.index != 1) return;
    final index = conversationDetailInitialTabIndex(conversation);
    if (index == 1) return;
    setState(() {
      selectedTab = ConversationTab.transcript;
    });
    _controller?.animateTo(index);
  }

  @override
  void dispose() {
    _cancelOwnedTimers();
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
      _controller?.animateTo(0);
    }
    try {
      await _seekToSegmentCallback!(start, end);
      if (mounted) HapticFeedback.lightImpact();
    } catch (_) {
      // Audio may be unavailable offline; search still opened the transcript tab.
    }
  }

  /// Navigate to adjacent conversation with slide animation.
  /// [direction]: 1 for older (swipe left), -1 for newer (swipe right)
  void _navigateToAdjacentConversation(int direction) {
    final detailProvider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);

    final currentConvoId = detailProvider.conversation.id;
    final currentDate = detailProvider.selectedDate;

    final adjacent = conversationProvider.getAdjacentConversation(currentConvoId, currentDate, direction);
    if (adjacent == null) {
      // At boundary, provide haptic feedback
      HapticFeedback.lightImpact();
      return;
    }

    HapticFeedback.selectionClick();

    // Navigate with slide animation (new page will initialize its own state)
    final currentTabIndex = _controller?.index ?? 1;

    Navigator.pushReplacement(
      context,
      PageRouteBuilder(
        pageBuilder: (context, animation, secondaryAnimation) => ConversationDetailPage(
          conversation: adjacent.conversation,
          isFromOnboarding: widget.isFromOnboarding,
          initialTabIndex: currentTabIndex,
        ),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          // Slide from right for older (direction=1), from left for newer (direction=-1)
          final begin = Offset(direction.toDouble(), 0.0);
          const end = Offset.zero;
          const curve = Curves.easeInOut;

          var tween = Tween(begin: begin, end: end).chain(CurveTween(curve: curve));
          var offsetAnimation = animation.drive(tween);

          return SlideTransition(position: offsetAnimation, child: child);
        },
        transitionDuration: const Duration(milliseconds: 250),
      ),
    );
  }

  void _handleMenuSelection(BuildContext context, String value, ConversationDetailProvider provider) async {
    // Track the menu action selection
    PlatformManager.instance.analytics.conversationThreeDotsMenuActionSelected(
      conversationId: provider.conversation.id,
      action: value,
    );

    switch (value) {
      case 'copy_transcript':
        _copyContent(context, provider.conversation.getTranscript(generate: true));
        break;
      case 'copy_summary':
        final conversation = provider.conversation;
        _copyContent(context, ConversationSummarySelection.select(conversation).content);
        break;
      case 'download_audio':
        await _downloadAudio(context, provider);
        break;
      case 'test_prompt':
        routeToPage(context, TestPromptsPage(conversation: provider.conversation));
        break;
      case 'reprocess':
        if (!provider.loadingReprocessConversation) {
          await provider.reprocessConversation();
        }
        break;
      case 'link_event':
        _handleLinkEvent(context, provider);
        break;
      case 'copy_conversation_id':
        Clipboard.setData(ClipboardData(text: provider.conversation.id));
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.conversationIdCopied)));
        HapticFeedback.lightImpact();
        break;
      case 'delete':
        _handleDelete(context, provider);
        break;
    }
  }

  void _handleLinkEvent(BuildContext context, ConversationDetailProvider provider) {
    // Check if Google Calendar is connected
    final integrationProvider = Provider.of<IntegrationProvider>(context, listen: false);
    final isConnected = integrationProvider.hasLoaded
        ? integrationProvider.isAppConnected(IntegrationApp.googleCalendar)
        : SharedPreferencesUtil().getBool('google_calendar_connected');

    if (!isConnected) {
      _showCalendarNotConnectedDialog(context);
      return;
    }

    // Show event picker directly
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => const CalendarEventPickerSheet(),
    );
  }

  void _showCalendarNotConnectedDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (c) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(context.l10n.googleCalendarNotConnected, style: const TextStyle(color: Colors.white)),
        content: Text(context.l10n.googleCalendarConnectPrompt, style: const TextStyle(color: Color(0xFF8E8E93))),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: Text(context.l10n.cancel, style: const TextStyle(color: Color(0xFF8E8E93))),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(c);
              Navigator.push(context, MaterialPageRoute(builder: (context) => const IntegrationsPage()));
            },
            child: Text(context.l10n.connect, style: const TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _handleDelete(BuildContext context, ConversationDetailProvider provider) {
    HapticFeedback.mediumImpact();
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (connectivityProvider.isConnected) {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () {
            final convoProvider = context.read<ConversationProvider>();
            convoProvider.deleteConversation(provider.conversation);
            Navigator.pop(context); // Close dialog
            Navigator.pop(context, {'deleted': true}); // Close detail page
          },
          context.l10n.deleteConversationTitle,
          context.l10n.deleteConversationMessage,
          okButtonText: context.l10n.confirm,
        ),
      );
    } else {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () => Navigator.pop(context),
          context.l10n.unableToDeleteConversation,
          context.l10n.noInternetConnection,
          singleButton: true,
          okButtonText: context.l10n.ok,
        ),
      );
    }
  }

  void _copyContent(BuildContext context, String content) {
    Clipboard.setData(ClipboardData(text: content));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.contentCopied)));
    HapticFeedback.lightImpact();
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

    AudioDownloadState currentState = AudioDownloadState.preparing;
    double currentProgress = 0.0;
    void Function(void Function())? updateSheet;

    // Show the progress sheet
    final sheetContext = context;
    showModalBottomSheet(
      context: sheetContext,
      isDismissible: false,
      enableDrag: false,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.5),
      builder: (context) => StatefulBuilder(
        builder: (context, setState) {
          updateSheet = setState;
          return AudioDownloadProgressSheet(state: currentState, progress: currentProgress);
        },
      ),
    );

    AudioDownloadService? service;
    try {
      service = AudioDownloadService();

      final file = await service.downloadAndCombineAudio(
        provider.conversation,
        onProgress: (progress) {
          currentProgress = progress;
          updateSheet?.call(() {});
        },
        onStageChange: (stage) {
          switch (stage) {
            case AudioDownloadStage.preparing:
              currentState = AudioDownloadState.preparing;
              break;
            case AudioDownloadStage.downloading:
              currentState = AudioDownloadState.downloading;
              break;
            case AudioDownloadStage.processing:
              currentState = AudioDownloadState.processing;
              break;
          }
          updateSheet?.call(() {});
        },
      );

      if (file != null) {
        currentState = AudioDownloadState.success;
        updateSheet?.call(() {});

        await _delay(const Duration(milliseconds: 500));

        if (sheetContext.mounted) {
          Navigator.maybeOf(sheetContext)?.pop();
        }

        final mimeType = file.path.endsWith('.mp3') ? 'audio/mpeg' : 'audio/wav';
        await Share.shareXFiles([
          XFile(file.path, mimeType: mimeType),
        ], sharePositionOrigin: shareSheetOrigin(_shareButtonKey));

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
        currentState = AudioDownloadState.error;
        updateSheet?.call(() {});

        await _delay(const Duration(seconds: 2));

        if (sheetContext.mounted) {
          Navigator.maybeOf(sheetContext)?.pop();
        }

        // Track failure (no audio available)
        PlatformManager.instance.analytics.audioShareFailed(
          conversationId: provider.conversation.id,
          errorMessage: 'No audio files available',
        );

        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.audioDownloadFailed),
              action: SnackBarAction(label: context.l10n.retry, onPressed: () => _downloadAudio(context, provider)),
            ),
          );
        }
      }
    } catch (e) {
      Logger.debug('Error downloading audio: $e');

      // Track failure
      PlatformManager.instance.analytics.audioShareFailed(
        conversationId: provider.conversation.id,
        errorMessage: e.toString(),
      );

      currentState = AudioDownloadState.error;
      updateSheet?.call(() {});

      await _delay(const Duration(seconds: 2));

      if (sheetContext.mounted) {
        Navigator.maybeOf(sheetContext)?.pop();
      }
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.audioDownloadFailed),
            action: SnackBarAction(label: context.l10n.retry, onPressed: () => _downloadAudio(context, provider)),
          ),
        );
      }
    } finally {
      service?.dispose();
      if (mounted) {
        setState(() {
          _isDownloadingAudio = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Empty shell on first build (before initState's setCachedConversation
    // post-frame); after init, an unresolved conversation pops the route.
    final detailProvider = context.watch<ConversationDetailProvider>();
    if (detailProvider.conversationOrNull == null) {
      if (_providerInitialized) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (Navigator.of(context).canPop()) {
            Navigator.of(context).pop();
          }
        });
      }
      return Scaffold(backgroundColor: Theme.of(context).colorScheme.primary);
    }

    return PopScope(
      canPop: true,
      child: MessageListener<ConversationDetailProvider>(
        showError: (error) {
          if (error == 'REPROCESS_FAILED') {
            ScaffoldMessenger.of(
              context,
            ).showSnackBar(SnackBar(content: Text(context.l10n.errorProcessingConversation)));
          }
        },
        showInfo: (info) {},
        child: Scaffold(
          key: scaffoldKey,
          extendBody: true,
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: Theme.of(context).colorScheme.primary,
            leading: Container(
              width: 36,
              height: 36,
              margin: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
              child: IconButton(
                padding: EdgeInsets.zero,
                tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                onPressed: () {
                  HapticFeedback.mediumImpact();
                  if (widget.isFromOnboarding) {
                    SchedulerBinding.instance.addPostFrameCallback((_) {
                      Navigator.pushAndRemoveUntil(
                        context,
                        MaterialPageRoute(builder: (context) => const HomePageWrapper()),
                        (route) => false,
                      );
                    });
                  } else {
                    Navigator.pop(context);
                  }
                },
                icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
              ),
            ),
            // No title: the tab bar below already names the active view, so a
            // header label only crowds the row with the back button and actions.
            // _getTabTitle still backs the `active_tab` search analytics property.
            titleSpacing: 0,
            actions: [
              Consumer<ConversationDetailProvider>(
                builder: (context, provider, child) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Ask about this conversation (#4515)
                        Container(
                          height: 44,
                          margin: const EdgeInsets.only(right: 8),
                          child: TextButton.icon(
                            key: const Key('conversation_ask_omi'),
                            style: TextButton.styleFrom(
                                shape: const StadiumBorder(),
                                foregroundColor: Colors.white,
                                backgroundColor: Colors.white.withValues(alpha: 0.12),
                                padding: const EdgeInsets.symmetric(horizontal: 12)),
                            label: Text(context.l10n.askOmi),
                            onPressed: () {
                              HapticFeedback.mediumImpact();
                              final convo = provider.conversation;
                              Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => ChatPage(
                                    isPivotBottom: false,
                                    initialChatContext: ChatPageContext(
                                      type: 'conversation',
                                      id: convo.id,
                                      title: convo.structured.title,
                                    ),
                                  ),
                                ),
                              );
                            },
                            icon: const FaIcon(FontAwesomeIcons.solidComments, size: 14.0, color: Colors.white),
                          ),
                        ),
                        // Star button (first) - toggle starred status
                        Container(
                          width: 44,
                          height: 44,
                          margin: const EdgeInsets.only(right: 4),
                          decoration: BoxDecoration(
                            color: provider.conversation.starred
                                ? Colors.amber.withValues(alpha: 0.3)
                                : Colors.grey.withValues(alpha: 0.3),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            tooltip: provider.conversation.starred
                                ? context.l10n.unstarConversation
                                : context.l10n.starConversation,
                            onPressed: _isTogglingStarred
                                ? null
                                : () async {
                                    setState(() {
                                      _isTogglingStarred = true;
                                    });
                                    HapticFeedback.mediumImpact();
                                    try {
                                      final newStarredState = !provider.conversation.starred;
                                      bool success = await setConversationStarred(
                                        provider.conversation.id,
                                        newStarredState,
                                      );
                                      if (!context.mounted) return;
                                      if (success) {
                                        provider.conversation.starred = newStarredState;
                                        // Update in conversation provider
                                        context.read<ConversationProvider>().updateConversationInSortedList(
                                              provider.conversation,
                                            );
                                        // Track star/unstar action
                                        PlatformManager.instance.analytics.conversationStarToggled(
                                          conversation: provider.conversation,
                                          starred: newStarredState,
                                          source: 'detail_page_button',
                                        );
                                      } else {
                                        ScaffoldMessenger.of(
                                          context,
                                        ).showSnackBar(SnackBar(content: Text(context.l10n.failedToUpdateStarred)));
                                      }
                                    } catch (e) {
                                      Logger.debug('Failed to toggle starred status: $e');
                                    } finally {
                                      if (mounted) {
                                        setState(() {
                                          _isTogglingStarred = false;
                                        });
                                      }
                                    }
                                  },
                            icon: _isTogglingStarred
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : FaIcon(
                                    provider.conversation.starred ? FontAwesomeIcons.solidStar : FontAwesomeIcons.star,
                                    size: 16.0,
                                    color: provider.conversation.starred ? Colors.amber : Colors.white,
                                  ),
                          ),
                        ),
                        // Share button (second) - directly share summary link
                        Container(
                          key: _shareButtonKey,
                          width: 44,
                          height: 44,
                          margin: const EdgeInsets.only(right: 4),
                          decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            tooltip: context.l10n.share,
                            onPressed: _isSharing
                                ? null
                                : () async {
                                    setState(() {
                                      _isSharing = true;
                                    });
                                    HapticFeedback.mediumImpact();
                                    try {
                                      // Directly share the summary link
                                      bool shared = await setConversationVisibility(provider.conversation.id);
                                      if (!shared) {
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(content: Text(context.l10n.conversationUrlNotShared)),
                                          );
                                        }
                                        setState(() {
                                          _isSharing = false;
                                        });
                                        return;
                                      }
                                      provider.updateVisibilityLocally(ConversationVisibility.shared);
                                      // Track share event
                                      PlatformManager.instance.analytics.conversationShared(
                                        conversation: provider.conversation,
                                        shareMethod: 'url_share',
                                      );
                                      shareConversationLink(
                                        provider.conversation,
                                        sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
                                      );
                                      // Small delay to let share sheet appear, then clear loading
                                      await _delay(const Duration(milliseconds: 150));
                                      if (!mounted) return;
                                      setState(() {
                                        _isSharing = false;
                                      });
                                    } catch (e) {
                                      setState(() {
                                        _isSharing = false;
                                      });
                                    }
                                  },
                            icon: _isSharing
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16.0, color: Colors.white),
                          ),
                        ),
                        // Developer Tools button (third) - iOS style pull-down menu
                        Container(
                          width: 44,
                          height: 44,
                          margin: const EdgeInsets.only(right: 4),
                          child: PullDownButton(
                            itemBuilder: (context) => [
                              if (_controller?.index != 2)
                                PullDownMenuItem(
                                  title: context.l10n.search,
                                  iconWidget: const FaIcon(FontAwesomeIcons.magnifyingGlass, size: 16),
                                  onTap: () {
                                    setState(() {
                                      _isSearching = !_isSearching;
                                      if (!_isSearching) {
                                        _searchQuery = '';
                                        _searchController.clear();
                                        _searchFocusNode.unfocus();
                                      } else {
                                        _searchFocusNode.requestFocus();
                                        PlatformManager.instance.analytics.conversationDetailSearchClicked(
                                          conversationId: provider.conversation.id,
                                        );
                                      }
                                    });
                                    HapticFeedback.mediumImpact();
                                  },
                                ),
                              PullDownMenuItem(
                                title: context.l10n.copyTranscript,
                                iconWidget: const FaIcon(FontAwesomeIcons.copy, size: 16),
                                onTap: () => _handleMenuSelection(context, 'copy_transcript', provider),
                              ),
                              PullDownMenuItem(
                                title: context.l10n.copySummary,
                                iconWidget: const FaIcon(FontAwesomeIcons.clone, size: 16),
                                onTap: () => _handleMenuSelection(context, 'copy_summary', provider),
                              ),
                              PullDownMenuItem(
                                title: context.l10n.copyConversationId,
                                iconWidget: const FaIcon(FontAwesomeIcons.clipboard, size: 16),
                                onTap: () => _handleMenuSelection(context, 'copy_conversation_id', provider),
                              ),
                              if (provider.conversation.hasAudio())
                                PullDownMenuItem(
                                  title: context.l10n.shareAudio,
                                  iconWidget: const FaIcon(FontAwesomeIcons.share, size: 16),
                                  onTap: _isDownloadingAudio
                                      ? null
                                      : () => _handleMenuSelection(context, 'download_audio', provider),
                                ),
                              // PullDownMenuItem(
                              //   title: 'Trigger Integration',
                              //   iconWidget: FaIcon(FontAwesomeIcons.paperPlane, size: 16),
                              //   onTap: () => _handleMenuSelection(context, 'trigger_integration', provider),
                              // ),
                              if (provider.conversation.calendarEvent == null)
                                PullDownMenuItem(
                                  title: 'Link Event',
                                  iconWidget: ClipRRect(
                                    borderRadius: BorderRadius.circular(4),
                                    child: Image.asset(
                                      'assets/integration_app_logos/google-calendar.png',
                                      width: 17,
                                      height: 17,
                                      fit: BoxFit.cover,
                                    ),
                                  ),
                                  onTap: () => _handleMenuSelection(context, 'link_event', provider),
                                ),
                              PullDownMenuItem(
                                title: context.l10n.testPrompt,
                                iconWidget: const FaIcon(FontAwesomeIcons.commentDots, size: 16),
                                onTap: () => _handleMenuSelection(context, 'test_prompt', provider),
                              ),
                              if (!provider.conversation.discarded)
                                PullDownMenuItem(
                                  title: context.l10n.reprocessConversation,
                                  iconWidget: const FaIcon(FontAwesomeIcons.arrowsRotate, size: 16),
                                  onTap: () => _handleMenuSelection(context, 'reprocess', provider),
                                ),
                              PullDownMenuItem(
                                title: context.l10n.deleteConversation,
                                iconWidget: const FaIcon(FontAwesomeIcons.trashCan, size: 16, color: Colors.red),
                                onTap: () => _handleMenuSelection(context, 'delete', provider),
                              ),
                            ],
                            buttonBuilder: (context, showMenu) => Semantics(
                              button: true,
                              label: context.l10n.moreOptions,
                              excludeSemantics: true,
                              onTap: () {
                                HapticFeedback.mediumImpact();
                                PlatformManager.instance.analytics.conversationThreeDotsMenuOpened(
                                  conversationId: provider.conversation.id,
                                );
                                showMenu();
                              },
                              child: GestureDetector(
                                onTap: () {
                                  HapticFeedback.mediumImpact();
                                  PlatformManager.instance.analytics.conversationThreeDotsMenuOpened(
                                    conversationId: provider.conversation.id,
                                  );
                                  showMenu();
                                },
                                child: Container(
                                  width: 36,
                                  height: 36,
                                  decoration: BoxDecoration(
                                    color: Colors.grey.withValues(alpha: 0.3),
                                    shape: BoxShape.circle,
                                  ),
                                  child: const Center(
                                    child: FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16.0, color: Colors.white),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ],
          ),
          // Removed floating action button as we now have the more button in the bottom bar
          body: Stack(
            children: [
              GestureDetector(
                excludeFromSemantics: true,
                behavior: HitTestBehavior.translucent,
                onTap: () {
                  // Close search if search bar is empty and user taps on content
                  if (_isSearching && _searchQuery.isEmpty) {
                    setState(() {
                      _isSearching = false;
                      _searchController.clear();
                      _searchFocusNode.unfocus();
                    });
                  }
                },
                // Horizontal swipe to navigate between conversations (mobile only)
                onHorizontalDragEnd: PlatformService.isMobile
                    ? (details) {
                        // Skip if on Action Items tab (to not interfere with Dismissible swipe-to-delete)
                        if (selectedTab == ConversationTab.actionItems) return;

                        final velocity = details.primaryVelocity ?? 0;
                        const swipeThreshold = 300.0; // minimum velocity to trigger navigation

                        if (velocity < -swipeThreshold) {
                          // Swipe left -> go to older conversation
                          _navigateToAdjacentConversation(1);
                        } else if (velocity > swipeThreshold) {
                          // Swipe right -> go to newer conversation
                          _navigateToAdjacentConversation(-1);
                        }
                      }
                    : null,
                child: Column(
                  children: [
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Builder(
                          builder: (context) {
                            return TabBarView(
                              controller: _controller,
                              physics: const NeverScrollableScrollPhysics(),
                              children: [
                                TranscriptWidgets(
                                  searchQuery: _searchQuery,
                                  currentResultIndex: getCurrentResultIndexForHighlighting(),
                                  onTapWhenSearchEmpty: () {
                                    if (_isSearching && _searchQuery.isEmpty) {
                                      setState(() {
                                        _isSearching = false;
                                        _searchController.clear();
                                        _searchFocusNode.unfocus();
                                      });
                                    }
                                  },
                                  onSegmentTap: (segment) async {
                                    if (selectedTab != ConversationTab.transcript) {
                                      setState(() {
                                        selectedTab = ConversationTab.transcript;
                                      });
                                      _controller!.animateTo(0);
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
                                  onTapWhenSearchEmpty: () {
                                    if (_isSearching && _searchQuery.isEmpty) {
                                      setState(() {
                                        _isSearching = false;
                                        _searchController.clear();
                                        _searchFocusNode.unfocus();
                                      });
                                    }
                                  },
                                ),
                                const ActionItemsTab(),
                              ],
                            );
                          },
                        ),
                      ),
                    ),
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
                  child: Consumer<ConversationDetailProvider>(
                    builder: (context, provider, child) {
                      final conversation = provider.conversation;
                      final hasActionItems =
                          conversation.structured.actionItems.where((item) => !item.deleted).isNotEmpty;
                      return ConversationBottomBar(
                        onAudioInteraction: () {
                          if (mounted && !_reviewInterrupted) setState(() => _reviewInterrupted = true);
                        },
                        mode: ConversationBottomBarMode.detail,
                        selectedTab: selectedTab,
                        conversation: conversation,
                        hasSegments: conversation.transcriptSegments.isNotEmpty ||
                            conversation.photos.isNotEmpty ||
                            conversation.externalIntegration != null,
                        hasActionItems: hasActionItems,
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
                          int index;
                          switch (tab) {
                            case ConversationTab.transcript:
                              index = 0;
                              break;
                            case ConversationTab.summary:
                              index = 1;
                              break;
                            case ConversationTab.actionItems:
                              index = 2;
                              break;
                          }
                          _controller!.animateTo(index);
                        },
                        onStopPressed: () {
                          // Empty since we don't show the stop button in detail mode
                        },
                      );
                    },
                  ),
                ),

              // Search overlay
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
                  bottom: 0,
                  child: Stack(
                    children: [
                      Positioned(
                        top: 0,
                        left: 0,
                        right: 0,
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          child: SafeArea(
                            child: TextField(
                              controller: _searchController,
                              focusNode: _searchFocusNode,
                              style: const TextStyle(color: Colors.white),
                              decoration: InputDecoration(
                                hintText: context.l10n.searchTranscriptOrSummary,
                                hintStyle: TextStyle(color: Colors.grey[400]),
                                prefixIcon: const Icon(Icons.search, color: Colors.white70),
                                suffixIcon: _searchQuery.isNotEmpty
                                    ? Container(
                                        width: _searchQuery.isNotEmpty ? 150 : 40,
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          mainAxisAlignment: MainAxisAlignment.end,
                                          children: [
                                            if (_searchQuery.isNotEmpty) ...[
                                              Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                                decoration: BoxDecoration(
                                                  color: Colors.grey.withValues(alpha: 0.3),
                                                  borderRadius: BorderRadius.circular(8),
                                                ),
                                                child: Text(
                                                  '$_currentSearchIndex/$_totalSearchResults',
                                                  style: const TextStyle(
                                                    color: Colors.white,
                                                    fontSize: 11,
                                                    fontWeight: FontWeight.w500,
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 4),
                                              Material(
                                                color: Colors.transparent,
                                                child: InkWell(
                                                  borderRadius: BorderRadius.circular(16),
                                                  onTap: _totalSearchResults > 0 ? () => _navigateSearch(false) : null,
                                                  child: Container(
                                                    width: 28,
                                                    height: 28,
                                                    decoration: BoxDecoration(borderRadius: BorderRadius.circular(18)),
                                                    child: Icon(
                                                      Icons.keyboard_arrow_up,
                                                      color: _totalSearchResults > 0 ? Colors.white70 : Colors.white30,
                                                      size: 22,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                              Material(
                                                color: Colors.transparent,
                                                child: InkWell(
                                                  borderRadius: BorderRadius.circular(16),
                                                  onTap: _totalSearchResults > 0 ? () => _navigateSearch(true) : null,
                                                  child: Container(
                                                    width: 28,
                                                    height: 28,
                                                    decoration: BoxDecoration(borderRadius: BorderRadius.circular(18)),
                                                    child: Icon(
                                                      Icons.keyboard_arrow_down,
                                                      color: _totalSearchResults > 0 ? Colors.white70 : Colors.white30,
                                                      size: 22,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 4),
                                            ],
                                            Material(
                                              color: Colors.transparent,
                                              child: InkWell(
                                                borderRadius: BorderRadius.circular(16),
                                                onTap: () {
                                                  setState(() {
                                                    _searchQuery = '';
                                                    _searchController.clear();
                                                    _totalSearchResults = 0;
                                                    _currentSearchIndex = 0;
                                                  });
                                                },
                                                child: Container(
                                                  width: 28,
                                                  height: 28,
                                                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(16)),
                                                  child: const Icon(Icons.clear, color: Colors.white70, size: 22),
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                      )
                                    : null,
                                filled: true,
                                fillColor: const Color(0xFF1C1C1E).withValues(alpha: 0.95),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: BorderSide.none,
                                ),
                                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              ),
                              onChanged: (value) {
                                setState(() {
                                  _searchQuery = value;
                                  _updateSearchResults();
                                  if (value.isNotEmpty) {
                                    // Track search query with results
                                    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
                                    PlatformManager.instance.analytics.conversationDetailSearchQueryEntered(
                                      conversationId: provider.conversation.id,
                                      query: value,
                                      resultsCount: _totalSearchResults,
                                      activeTab: _getTabTitle(context, selectedTab),
                                    );
                                  }
                                });
                              },
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Bottom sheet for picking a calendar event to link
class CalendarEventPickerSheet extends StatefulWidget {
  const CalendarEventPickerSheet({super.key});

  @override
  State<CalendarEventPickerSheet> createState() => _CalendarEventPickerSheetState();
}

class _CalendarEventPickerSheetState extends State<CalendarEventPickerSheet> {
  List<CalendarEventLink> _events = [];
  String? _suggestedEventId;
  bool _isLoading = true;
  bool _isLinking = false;
  String? _linkingEventId;

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final events = await provider.listCalendarEventsForPicker();

    if (mounted) {
      final conversation = provider.conversation;
      final conversationStart = conversation.startedAt ?? conversation.createdAt;
      final conversationEnd = conversation.finishedAt ?? conversationStart.add(const Duration(hours: 1));

      String? bestMatchId;
      double bestOverlapSeconds = 0;

      for (final event in events) {
        final overlapStart = event.startTime.isAfter(conversationStart) ? event.startTime : conversationStart;
        final overlapEnd = event.endTime.isBefore(conversationEnd) ? event.endTime : conversationEnd;
        final overlapDuration = overlapEnd.difference(overlapStart).inSeconds.toDouble();

        if (overlapDuration > 0) {
          final eventDuration = event.endTime.difference(event.startTime).inSeconds.toDouble();
          final overlapPercentage = eventDuration > 0 ? overlapDuration / eventDuration : 0;

          if ((overlapDuration >= 300 || overlapPercentage >= 0.5) && overlapDuration > bestOverlapSeconds) {
            bestOverlapSeconds = overlapDuration;
            bestMatchId = event.eventId;
          }
        }
      }

      final sortedEvents = List<CalendarEventLink>.from(events);
      if (bestMatchId != null) {
        sortedEvents.sort((a, b) {
          if (a.eventId == bestMatchId) return -1;
          if (b.eventId == bestMatchId) return 1;
          return a.startTime.compareTo(b.startTime);
        });
      }

      setState(() {
        _events = sortedEvents;
        _suggestedEventId = bestMatchId;
        _isLoading = false;
      });
    }
  }

  String _formatTime(DateTime time) {
    return dateTimeFormat('h:mm a', time);
  }

  String _formatDate(DateTime time) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    final dateOnly = DateTime(time.year, time.month, time.day);

    if (dateOnly == today) {
      return 'Today';
    } else if (dateOnly == yesterday) {
      return 'Yesterday';
    } else if (time.year == now.year) {
      return dateTimeFormat('MMM d', time);
    } else {
      return dateTimeFormat('MMM d, yyyy', time);
    }
  }

  Future<void> _linkEvent(CalendarEventLink event) async {
    setState(() {
      _isLinking = true;
      _linkingEventId = event.eventId;
    });
    HapticFeedback.mediumImpact();

    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final linked = await provider.linkCalendarEvent(event.eventId);

    if (!mounted) return;

    if (linked != null) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.linkedToEvent(event.title))));
    } else {
      setState(() {
        _isLinking = false;
        _linkingEventId = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.failedToLinkCalendarEvent)));
    }
  }

  Widget _buildShimmerList() {
    return Shimmer.fromColors(
      baseColor: Colors.grey.shade800,
      highlightColor: Colors.grey.shade600,
      child: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: 4,
        itemBuilder: (context, index) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(8)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        height: 14,
                        width: double.infinity,
                        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(4)),
                      ),
                      const SizedBox(height: 10),
                      Container(
                        height: 12,
                        width: 140,
                        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(4)),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 14),
                Container(
                  width: 22,
                  height: 22,
                  decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildEventTile(CalendarEventLink event, bool isSuggested, bool isLinkingThis) {
    return GestureDetector(
      onTap: _isLinking ? null : () => _linkEvent(event),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.asset(
                'assets/integration_app_logos/google-calendar.png',
                width: 36,
                height: 36,
                fit: BoxFit.cover,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    event.title,
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  if (isSuggested)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.deepPurple.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Text(
                        'Suggested',
                        style: TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.w600),
                      ),
                    )
                  else
                    Text(
                      '${_formatDate(event.startTime)}, ${_formatTime(event.startTime)} – ${_formatTime(event.endTime)}',
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 14),
            _isLinking && isLinkingThis
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                  )
                : Icon(Icons.add_circle_outline, color: _isLinking ? Colors.grey.shade700 : Colors.grey, size: 22),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 36,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey.shade600, borderRadius: BorderRadius.circular(2)),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Text(
                  'Link Event',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: const Icon(Icons.close, color: Colors.grey, size: 24),
                ),
              ],
            ),
          ),
          const Divider(color: Color(0xFF2A2A2E), height: 1),
          Flexible(
            child: _isLoading
                ? _buildShimmerList()
                : _events.isEmpty
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.all(40),
                          child: Text(
                            'No calendar events found around this time.',
                            style: TextStyle(color: Colors.grey, fontSize: 15),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      )
                    : ListView.separated(
                        shrinkWrap: true,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: _events.length,
                        separatorBuilder: (_, __) =>
                            const Divider(color: Color(0xFF2A2A2E), height: 1, indent: 16, endIndent: 16),
                        itemBuilder: (context, index) {
                          final event = _events[index];
                          final isLinkingThis = _linkingEventId == event.eventId;
                          final isSuggested = event.eventId == _suggestedEventId;
                          return _buildEventTile(event, isSuggested, isLinkingThis);
                        },
                      ),
          ),
          SizedBox(height: MediaQuery.of(context).padding.bottom + 8),
        ],
      ),
    );
  }
}

class TranscriptWidgets extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;

  const TranscriptWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
  });

  @override
  State<TranscriptWidgets> createState() => _TranscriptWidgetsState();
}

class _TranscriptWidgetsState extends State<TranscriptWidgets> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Listener(
      onPointerDown: (PointerDownEvent event) {
        FocusScope.of(context).unfocus();
        if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
          widget.onTapWhenSearchEmpty!();
        }
      },
      child: GestureDetector(
        excludeFromSemantics: true,
        behavior: HitTestBehavior.translucent,
        onTap: () {
          FocusScope.of(context).unfocus();
          if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
            widget.onTapWhenSearchEmpty!();
          }
        },
        child: Consumer<ConversationDetailProvider>(
          builder: (context, provider, child) {
            final conversation = provider.conversation;
            final segments = conversation.transcriptSegments;
            final photos = conversation.photos;

            if (segments.isEmpty && photos.isEmpty) {
              return Padding(
                padding: const EdgeInsets.only(top: 32),
                child: ExpandableTextWidget(
                  text: (provider.conversation.externalIntegration?.text ?? '').decodeString,
                  maxLines: 1000,
                  linkColor: Colors.grey.shade300,
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                  toggleExpand: () {
                    provider.toggleIsTranscriptExpanded();
                  },
                  isExpanded: provider.isTranscriptExpanded,
                ),
              );
            }

            return Column(children: [
              SpeakerSummaryAction(provider: provider),
              Expanded(
                  child: getTranscriptWidget(
                false,
                segments,
                photos,
                null,
                conversationId: conversation.id,
                horizontalMargin: false,
                topMargin: false,
                canDisplaySeconds: provider.canDisplaySeconds,
                isConversationDetail: true,
                bottomMargin: 150,
                searchQuery: widget.searchQuery,
                currentResultIndex: widget.currentResultIndex,
                onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
                onSegmentTap: widget.onSegmentTap,
                onEditSegmentText: (segmentIndex) {
                  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                  if (!connectivityProvider.isConnected) {
                    ConnectivityProvider.showNoInternetDialog(context);
                    return;
                  }
                  final segments = provider.conversation.transcriptSegments;
                  final segment = segments[segmentIndex];
                  final person =
                      segment.personId != null ? SharedPreferencesUtil().getPersonById(segment.personId!) : null;
                  final speakerName = person?.name ??
                      context.l10n
                          .speakerWithId('${TranscriptSegment.getDisplaySpeakerId(segment.speakerId, segments)}');
                  PlatformManager.instance.analytics.editSegmentTextStarted();
                  bool saved = false;
                  showEditSegmentBottomSheet(
                    context,
                    segment: segment,
                    speakerName: speakerName,
                    onSave: (newText) {
                      saved = true;
                      PlatformManager.instance.analytics.editSegmentTextSaved();
                      provider.saveEditingSegmentText(segmentIndex, newText);
                    },
                    onDismissed: () {
                      if (!saved) PlatformManager.instance.analytics.editSegmentTextCancelled();
                    },
                  );
                },
                editSegment: (segmentId, speakerId) {
                  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                  if (!connectivityProvider.isConnected) {
                    ConnectivityProvider.showNoInternetDialog(context);
                    return;
                  }
                  showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    backgroundColor: Colors.black,
                    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
                    builder: (context) {
                      return Consumer<PeopleProvider>(
                        builder: (context, peopleProvider, child) {
                          return NameSpeakerBottomSheet(
                            speakerId: speakerId,
                            segmentId: segmentId,
                            segments: provider.conversation.transcriptSegments,
                            onSpeakerAssigned: (speakerId, personId, personName, segmentIds, applyToSpeaker) async {
                              final targetId = provider.conversation.id;
                              final finalPersonId = personId.isEmpty
                                  ? (await peopleProvider.createPersonProvider(personName))?.id
                                  : personId;
                              if (finalPersonId == null || finalPersonId.isEmpty) return false;
                              final saved = await provider.assignSpeaker(segmentIds, finalPersonId,
                                  speakerId: applyToSpeaker ? speakerId : null, expectedConversationId: targetId);
                              if (saved) {
                                PlatformManager.instance.analytics
                                    .taggedSegment(finalPersonId == 'user' ? 'User' : 'User Person');
                              }
                              return saved;
                            },
                          );
                        },
                      );
                    },
                  );
                },
              )),
            ]);
          },
        ),
      ),
    );
  }
}

class ActionItemDetailWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;

  const ActionItemDetailWidget({super.key, required this.actionItem, required this.conversationId});

  @override
  State<ActionItemDetailWidget> createState() => _ActionItemDetailWidgetState();
}

class _ActionItemDetailWidgetState extends State<ActionItemDetailWidget> {
  static final Map<String, bool> _pendingStates = {}; // Track pending states by description
  Timer? _pendingClearTimer;

  @override
  void dispose() {
    _pendingClearTimer?.cancel();
    _pendingClearTimer = null;
    // Clean up any pending state for this item when widget is disposed
    _pendingStates.remove(widget.actionItem.description);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        // Find the current action item by description to get the latest state
        final actionItem = provider.conversation.structured.actionItems.firstWhere(
          (item) => item.description == widget.actionItem.description,
          orElse: () => widget.actionItem,
        );

        // Check if this specific item has a pending state change
        final isCompleted = _pendingStates.containsKey(widget.actionItem.description)
            ? _pendingStates[widget.actionItem.description]!
            : actionItem.completed;

        return AnimatedOpacity(
          opacity: 1.0,
          duration: const Duration(milliseconds: 300),
          child: Container(
            decoration: BoxDecoration(
              color: Colors.grey[900],
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(color: Colors.black.withValues(alpha: 0.1), blurRadius: 4, offset: const Offset(0, 2)),
              ],
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () {
                  HapticFeedback.lightImpact();
                  // TODO: Add edit functionality if needed
                },
                borderRadius: BorderRadius.circular(16),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 16.0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 20,
                        height: 20,
                        child: Transform.translate(
                          offset: const Offset(0, 2),
                          child: GestureDetector(
                            onTap: () => _toggleCompletion(provider, actionItem),
                            child: Container(
                              width: 20,
                              height: 20,
                              decoration: BoxDecoration(
                                color: isCompleted ? Colors.green : Colors.transparent,
                                border: Border.all(color: isCompleted ? Colors.green : Colors.grey, width: 2),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: isCompleted ? const Icon(Icons.check, size: 14, color: Colors.white) : null,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Text(
                          actionItem.description,
                          style: TextStyle(
                            color: isCompleted ? Colors.grey : Colors.white,
                            decoration: isCompleted ? TextDecoration.lineThrough : null,
                            decorationColor: Colors.grey,
                            fontSize: 15,
                            height: 1.4,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  void _toggleCompletion(ConversationDetailProvider provider, ActionItem actionItem) async {
    // Haptic feedback
    HapticFeedback.lightImpact();

    final newValue = !actionItem.completed;
    final itemDescription = widget.actionItem.description;

    // Update pending state immediately for instant visual feedback
    setState(() {
      _pendingStates[itemDescription] = newValue;
    });

    // Get ConversationProvider for global state management
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);

    try {
      // Update global state immediately
      await conversationProvider.updateGlobalActionItemState(provider.conversation, itemDescription, newValue);

      // Wait for 200ms before clearing pending state (allows user to see the change before item moves)
      _pendingClearTimer?.cancel();
      _pendingClearTimer = Timer(const Duration(milliseconds: 200), () {
        _pendingClearTimer = null;
        if (mounted) {
          setState(() {
            _pendingStates.remove(itemDescription); // Clear pending state so item moves to correct section
          });
        }
      });

      // Track analytics - find the current index for analytics
      final currentIndex = provider.conversation.structured.actionItems.indexWhere(
        (item) => item.description == itemDescription,
      );
      if (currentIndex != -1) {
        if (newValue) {
          PlatformManager.instance.analytics.checkedActionItem(provider.conversation, currentIndex);
        } else {
          PlatformManager.instance.analytics.uncheckedActionItem(provider.conversation, currentIndex);
        }
      }
    } catch (e) {
      // If there's an error, revert pending state
      if (mounted) {
        setState(() {
          _pendingStates.remove(itemDescription);
        });
      }
      Logger.debug('Error updating action item state: $e');
    }
  }
}

class ActionItemsTab extends StatelessWidget {
  const ActionItemsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final allActionItems = provider.conversation.structured.actionItems.where((item) => !item.deleted).toList();
        final incompleteItems = allActionItems.where((item) => !item.completed).toList();
        final completedItems = allActionItems.where((item) => item.completed).toList();

        if (allActionItems.isEmpty) {
          return _buildEmptyState(context);
        }

        return CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // Header section with title and count
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(8.0, 24.0, 8.0, 0.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'To-Do',
                          style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(color: Colors.grey[800], borderRadius: BorderRadius.circular(12)),
                          child: Text(
                            '${incompleteItems.length}',
                            style: const TextStyle(color: Colors.grey, fontSize: 14, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            ),

            // Incomplete action items
            if (incompleteItems.isNotEmpty)
              SliverList(
                delegate: SliverChildBuilderDelegate((context, index) {
                  final item = incompleteItems[index];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    child: ActionItemDetailWidget(actionItem: item, conversationId: provider.conversation.id),
                  );
                }, childCount: incompleteItems.length),
              )
            else
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8.0),
                  child: Container(
                    height: 52,
                    decoration: BoxDecoration(color: Colors.grey[900], borderRadius: BorderRadius.circular(16)),
                    child: Center(
                      child: Text(
                        'No pending action items',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                      ),
                    ),
                  ),
                ),
              ),

            // Completed section header
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(8.0, 24.0, 8.0, 8.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            const Text(
                              'Completed',
                              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.grey[800],
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                '${completedItems.length}',
                                style: const TextStyle(color: Colors.grey, fontSize: 14, fontWeight: FontWeight.w500),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            // Completed action items
            if (completedItems.isNotEmpty)
              SliverList(
                delegate: SliverChildBuilderDelegate((context, index) {
                  final item = completedItems[index];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    child: ActionItemDetailWidget(actionItem: item, conversationId: provider.conversation.id),
                  );
                }, childCount: completedItems.length),
              )
            else
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8.0),
                  child: Container(
                    height: 52,
                    decoration: BoxDecoration(color: Colors.grey[900], borderRadius: BorderRadius.circular(16)),
                    child: Center(
                      child: Text(
                        'No completed items yet',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                      ),
                    ),
                  ),
                ),
              ),

            const SliverPadding(padding: EdgeInsets.only(bottom: 150)),
          ],
        );
      },
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 72, color: Colors.grey.shade400),
            const SizedBox(height: 24),
            Text(
              'No Action Items',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              'Tasks and to-dos from this conversation will appear here once they are created.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 16, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }
}
