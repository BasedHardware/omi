import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:share_plus/share_plus.dart';
import 'package:tuple/tuple.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'conversation_detail_provider.dart';
import 'test_prompts.dart';
import 'widgets/name_speaker_sheet.dart';
import 'widgets/share_to_contacts_sheet.dart';

// import 'package:omi/backend/preferences.dart';

// import 'share.dart';
// import 'package:omi/pages/settings/developer.dart';
// import 'package:omi/backend/http/webhooks.dart';

class ConversationDetailPage extends StatefulWidget {
  final ServerConversation conversation;
  final bool isFromOnboarding;
  final bool openShareToContactsOnLoad;
  final int initialTabIndex;

  const ConversationDetailPage({
    super.key,
    this.isFromOnboarding = false,
    required this.conversation,
    this.openShareToContactsOnLoad = false,
    this.initialTabIndex = 1, // Default to summary tab
  });

  @override
  State<ConversationDetailPage> createState() => _ConversationDetailPageState();
}

class _ConversationDetailPageState extends State<ConversationDetailPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  final GlobalKey _shareButtonKey = GlobalKey();
  TabController? _controller;
  final AppReviewService _appReviewService = AppReviewService();
  ConversationTab selectedTab = ConversationTab.summary;
  bool _isSharing = false;
  bool _isTogglingStarred = false;

  // Search functionality
  bool _isSearching = false;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();
  int _currentSearchIndex = 0;
  int _totalSearchResults = 0;
  List<int> _searchResultPositions = []; // Track positions of search results

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
      final summarizedApp = provider.getSummarizedApp();
      if (summarizedApp != null && summarizedApp.content.trim().isNotEmpty) {
        final appContent = summarizedApp.content.trim().decodeString.toLowerCase();
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

    _controller = TabController(length: 3, vsync: this, initialIndex: widget.initialTabIndex);
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
          MixpanelManager().conversationDetailTabChanged(tabName);
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

      // Ensure the provider has the conversation data from the widget parameter
      provider.setCachedConversation(widget.conversation);

      conversationProvider.groupConversationsByDate();

      // Find the proper date and index for this conversation in the grouped conversations
      final result = conversationProvider.getConversationDateAndIndex(widget.conversation);
      if (result != null) {
        final (date, index) = result;
        provider.updateConversation(widget.conversation.id, date);
      } else {
        final effectiveDate = widget.conversation.startedAt ?? widget.conversation.createdAt;
        provider.selectedDate = DateTime(effectiveDate.year, effectiveDate.month, effectiveDate.day);
      }

      await provider.initConversation();
      if (provider.conversation.appResults.isEmpty) {
        final date = provider.selectedDate;
        final idx = conversationProvider.getConversationIndexById(provider.conversation.id, date);
        if (idx != -1) {
          await conversationProvider.updateSearchedConvoDetails(provider.conversation.id, date, idx);
        }
        provider.updateConversation(provider.conversation.id, provider.selectedDate);
      }

      // Check if this is the first conversation and show app review prompt
      if (await _appReviewService.isFirstConversation()) {
        if (mounted) {
          await _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: true);
        }
      }

      // Auto-open share to contacts sheet if requested (from important conversation notification)
      if (widget.openShareToContactsOnLoad && mounted) {
        // Small delay to ensure the page is fully rendered
        await Future.delayed(const Duration(milliseconds: 500));
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

  @override
  void dispose() {
    _controller?.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
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
    MixpanelManager().conversationThreeDotsMenuActionSelected(
      conversationId: provider.conversation.id,
      action: value,
    );

    switch (value) {
      case 'copy_transcript':
        _copyContent(context, provider.conversation.getTranscript(generate: true));
        break;
      case 'copy_summary':
        // Use app-generated summary if available, otherwise fall back to structured summary
        final conversation = provider.conversation;
        final summaryContent =
            conversation.appResults.isNotEmpty && conversation.appResults[0].content.trim().isNotEmpty
                ? conversation.appResults[0].content.trim()
                : conversation.structured.toString();
        _copyContent(context, summaryContent);
        break;
      // case 'export_transcript':
      //   showShareBottomSheet(context, provider.conversation, (fn) {});
      //   break;
      // case 'export_summary':
      //   showShareBottomSheet(context, provider.conversation, (fn) {});
      //   break;
      // case 'copy_raw_transcript':
      //   _copyContent(context, provider.conversation.getTranscript());
      //   break;
      // case 'copy_conversation_raw':
      //   _copyContent(context, provider.conversation.toJson().toString());
      //   break;
      // case 'trigger_integration':
      //   _triggerWebhookIntegration(context, provider.conversation);
      //   break;
      case 'test_prompt':
        routeToPage(context, TestPromptsPage(conversation: provider.conversation));
        break;
      case 'reprocess':
        if (!provider.loadingReprocessConversation) {
          await provider.reprocessConversation();
        }
        break;
      case 'delete':
        _handleDelete(context, provider);
        break;
    }
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
            {
              final convoProvider = context.read<ConversationProvider>();
              final date = provider.selectedDate;
              final idx = convoProvider.getConversationIndexById(provider.conversation.id, date);
              convoProvider.deleteConversation(provider.conversation, idx);
            }
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(context.l10n.contentCopied)),
    );
    HapticFeedback.lightImpact();
  }

  // void _triggerWebhookIntegration(BuildContext context, ServerConversation conversation) {
  //   if (SharedPreferencesUtil().webhookOnConversationCreated.isEmpty) {
  //     showDialog(
  //       context: context,
  //       builder: (c) => getDialog(
  //         context,
  //         () => Navigator.pop(context),
  //         () {
  //           Navigator.pop(context);
  //           routeToPage(context, const DeveloperSettingsPage());
  //         },
  //         'Webhook URL not set',
  //         'Please set the webhook URL in developer settings to use this feature.',
  //         okButtonText: 'Settings',
  //       ),
  //     );
  //     return;
  //   }
  //
  //   webhookOnConversationCreatedCall(conversation, returnRawBody: true).then((response) {
  //     showDialog(
  //       context: context,
  //       builder: (c) => getDialog(
  //         context,
  //         () => Navigator.pop(context),
  //         () => Navigator.pop(context),
  //         'Result:',
  //         response,
  //         okButtonText: 'Ok',
  //         singleButton: true,
  //       ),
  //     );
  //   });
  // }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: MessageListener<ConversationDetailProvider>(
        showError: (error) {
          if (error == 'REPROCESS_FAILED') {
            ScaffoldMessenger.of(context)
                .showSnackBar(SnackBar(content: Text(context.l10n.errorProcessingConversation)));
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
              decoration: BoxDecoration(
                color: Colors.grey.withOpacity(0.3),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.mediumImpact();
                  if (widget.isFromOnboarding) {
                    SchedulerBinding.instance.addPostFrameCallback((_) {
                      Navigator.pushAndRemoveUntil(
                          context, MaterialPageRoute(builder: (context) => const HomePageWrapper()), (route) => false);
                    });
                  } else {
                    Navigator.pop(context);
                  }
                },
                icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
              ),
            ),
            title: Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child: Text(
                  _getTabTitle(context, selectedTab),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            titleSpacing: 0,
            actions: [
              Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Star button (first) - toggle starred status
                      Container(
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: provider.conversation.starred
                              ? Colors.amber.withValues(alpha: 0.3)
                              : Colors.grey.withValues(alpha: 0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
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
                                    if (!mounted) return;
                                    if (success) {
                                      provider.conversation.starred = newStarredState;
                                      // Update in conversation provider
                                      context.read<ConversationProvider>().updateConversationInSortedList(
                                            provider.conversation,
                                          );
                                      // Track star/unstar action
                                      MixpanelManager().conversationStarToggled(
                                        conversation: provider.conversation,
                                        starred: newStarredState,
                                        source: 'detail_page_button',
                                      );
                                    } else {
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(content: Text(context.l10n.failedToUpdateStarred)),
                                      );
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
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: Colors.grey.withOpacity(0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
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
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(content: Text(context.l10n.conversationUrlNotShared)),
                                      );
                                      setState(() {
                                        _isSharing = false;
                                      });
                                      return;
                                    }
                                    String content = 'https://h.omi.me/memories/${provider.conversation.id}';
                                    // Track share event
                                    MixpanelManager().conversationShared(
                                      conversation: provider.conversation,
                                      shareMethod: 'url_share',
                                    );
                                    // Start sharing and get the position for iOS
                                    final RenderBox? box =
                                        _shareButtonKey.currentContext?.findRenderObject() as RenderBox?;
                                    if (box != null) {
                                      final Offset position = box.localToGlobal(Offset.zero);
                                      final Size size = box.size;
                                      Share.share(
                                        content,
                                        subject: provider.conversation.structured.title,
                                        sharePositionOrigin:
                                            Rect.fromLTWH(position.dx, position.dy, size.width, size.height),
                                      );
                                    } else {
                                      Share.share(content, subject: provider.conversation.structured.title);
                                    }
                                    // Small delay to let share sheet appear, then clear loading
                                    await Future.delayed(const Duration(milliseconds: 150));
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
                      // Search button (second) - only show on transcript and summary tabs
                      if (_controller?.index != 2)
                        Container(
                          width: 36,
                          height: 36,
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(
                            color: _isSearching ? Colors.deepPurple.withOpacity(0.8) : Colors.grey.withOpacity(0.3),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            padding: EdgeInsets.zero,
                            onPressed: () {
                              setState(() {
                                _isSearching = !_isSearching;
                                if (!_isSearching) {
                                  _searchQuery = '';
                                  _searchController.clear();
                                  _searchFocusNode.unfocus();
                                } else {
                                  _searchFocusNode.requestFocus();
                                  MixpanelManager().conversationDetailSearchClicked(
                                    conversationId: provider.conversation.id,
                                  );
                                }
                              });
                              HapticFeedback.mediumImpact();
                            },
                            icon: const FaIcon(FontAwesomeIcons.magnifyingGlass, size: 16.0, color: Colors.white),
                          ),
                        ),
                      // Developer Tools button (third) - iOS style pull-down menu
                      Container(
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        child: PullDownButton(
                          itemBuilder: (context) => [
                            PullDownMenuItem(
                              title: context.l10n.copyTranscript,
                              iconWidget: FaIcon(FontAwesomeIcons.copy, size: 16),
                              onTap: () => _handleMenuSelection(context, 'copy_transcript', provider),
                            ),
                            PullDownMenuItem(
                              title: context.l10n.copySummary,
                              iconWidget: FaIcon(FontAwesomeIcons.clone, size: 16),
                              onTap: () => _handleMenuSelection(context, 'copy_summary', provider),
                            ),
                            // PullDownMenuItem(
                            //   title: 'Trigger Integration',
                            //   iconWidget: FaIcon(FontAwesomeIcons.paperPlane, size: 16),
                            //   onTap: () => _handleMenuSelection(context, 'trigger_integration', provider),
                            // ),
                            PullDownMenuItem(
                              title: context.l10n.testPrompt,
                              iconWidget: FaIcon(FontAwesomeIcons.commentDots, size: 16),
                              onTap: () => _handleMenuSelection(context, 'test_prompt', provider),
                            ),
                            if (!provider.conversation.discarded)
                              PullDownMenuItem(
                                title: context.l10n.reprocessConversation,
                                iconWidget: FaIcon(FontAwesomeIcons.arrowsRotate, size: 16),
                                onTap: () => _handleMenuSelection(context, 'reprocess', provider),
                              ),
                            PullDownMenuItem(
                              title: context.l10n.deleteConversation,
                              iconWidget: FaIcon(FontAwesomeIcons.trashCan, size: 16, color: Colors.red),
                              onTap: () => _handleMenuSelection(context, 'delete', provider),
                            ),
                          ],
                          buttonBuilder: (context, showMenu) => GestureDetector(
                            onTap: () {
                              HapticFeedback.mediumImpact();
                              MixpanelManager().conversationThreeDotsMenuOpened(
                                conversationId: provider.conversation.id,
                              );
                              showMenu();
                            },
                            child: Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(
                                color: Colors.grey.withOpacity(0.3),
                                shape: BoxShape.circle,
                              ),
                              child: const Center(
                                child: FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16.0, color: Colors.white),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              }),
            ],
          ),
          // Removed floating action button as we now have the more button in the bottom bar
          body: Stack(
            children: [
              GestureDetector(
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
                        child: Builder(builder: (context) {
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
                              ),
                              SummaryTab(
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
                              ActionItemsTab(),
                            ],
                          );
                        }),
                      ),
                    ),
                  ],
                ),
              ),

              // Floating bottom bar
              Positioned(
                bottom: 32,
                left: 0,
                right: 0,
                child: Consumer<ConversationDetailProvider>(
                  builder: (context, provider, child) {
                    final conversation = provider.conversation;
                    final hasActionItems =
                        conversation.structured.actionItems.where((item) => !item.deleted).isNotEmpty;
                    return ConversationBottomBar(
                      mode: ConversationBottomBarMode.detail,
                      selectedTab: selectedTab,
                      conversation: conversation,
                      hasSegments: conversation.transcriptSegments.isNotEmpty ||
                          conversation.photos.isNotEmpty ||
                          conversation.externalIntegration != null,
                      hasActionItems: hasActionItems,
                      onTabSelected: (tab) {
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

              // thinh's comment: temporary disabled
              //// Unassigned segments notification - positioned above the bottom bar
              //Positioned(
              //  bottom: 88, // Position above the bottom bar
              //  left: 16,
              //  right: 16,
              //  child: Selector<ConversationDetailProvider, ({bool shouldShow, int count})>(
              //    selector: (context, provider) {
              //      final conversation = provider.conversation;
              //      if (conversation == null) {
              //        return (
              //          count: 0,
              //          shouldShow: false,
              //        );
              //      }
              //      return (
              //        count: conversation.unassignedSegmentsLength(),
              //        shouldShow: provider.showUnassignedFloatingButton && (selectedTab == ConversationTab.transcript),
              //      );
              //    },
              //    builder: (context, value, child) {
              //      if (value.count == 0 || !value.shouldShow) return const SizedBox.shrink();
              //      return Container(
              //        padding: const EdgeInsets.symmetric(
              //          vertical: 8,
              //          horizontal: 16,
              //        ),
              //        decoration: BoxDecoration(
              //          borderRadius: BorderRadius.circular(16),
              //          color: const Color(0xFF1F1F25),
              //          boxShadow: [
              //            BoxShadow(
              //              color: Colors.black.withOpacity(0.3),
              //              spreadRadius: 1,
              //              blurRadius: 2,
              //              offset: const Offset(0, 1),
              //            ),
              //          ],
              //        ),
              //        child: Row(
              //          mainAxisAlignment: MainAxisAlignment.spaceBetween,
              //          children: [
              //            Row(
              //              children: [
              //                InkWell(
              //                  onTap: () {
              //                    var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
              //                    provider.setShowUnassignedFloatingButton(false);
              //                  },
              //                  child: const Icon(
              //                    Icons.close,
              //                    color: Colors.white,
              //                  ),
              //                ),
              //                const SizedBox(width: 8),
              //                Text(
              //                  "${value.count} unassigned segment${value.count == 1 ? '' : 's'}",
              //                  style: const TextStyle(
              //                    color: Colors.white,
              //                    fontSize: 16,
              //                  ),
              //                ),
              //              ],
              //            ),
              //            ElevatedButton(
              //              style: ElevatedButton.styleFrom(
              //                backgroundColor: Colors.deepPurple.withOpacity(0.5),
              //                shape: RoundedRectangleBorder(
              //                  borderRadius: BorderRadius.circular(16),
              //                ),
              //              ),
              //              onPressed: () {
              //                var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
              //                var speakerId = provider.conversation.speakerWithMostUnassignedSegments();
              //                var segmentIdx = provider.conversation.firstSegmentIndexForSpeaker(speakerId);
              //                showModalBottomSheet(
              //                  context: context,
              //                  isScrollControlled: true,
              //                  backgroundColor: Colors.black,
              //                  shape: const RoundedRectangleBorder(
              //                    borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
              //                  ),
              //                  builder: (context) {
              //                    return NameSpeakerBottomSheet(
              //                      segmentIdx: segmentIdx,
              //                      speakerId: speakerId,
              //                    );
              //                  },
              //                );
              //              },
              //              child: const Text(
              //                "Tag",
              //                style: TextStyle(
              //                  color: Colors.white,
              //                  fontWeight: FontWeight.bold,
              //                ),
              //              ),
              //            ),
              //          ],
              //        ),
              //      );
              //    },
              //  ),
              //),
              // Search overlay
              if (_isSearching)
                Positioned(
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
                                hintText: 'Search transcript or summary...',
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
                                                  color: Colors.grey.withOpacity(0.3),
                                                  borderRadius: BorderRadius.circular(8),
                                                ),
                                                child: Text(
                                                  '$_currentSearchIndex/$_totalSearchResults',
                                                  style: const TextStyle(
                                                      color: Colors.white, fontSize: 11, fontWeight: FontWeight.w500),
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
                                                    decoration: BoxDecoration(
                                                      borderRadius: BorderRadius.circular(18),
                                                    ),
                                                    child: Icon(Icons.keyboard_arrow_up,
                                                        color:
                                                            _totalSearchResults > 0 ? Colors.white70 : Colors.white30,
                                                        size: 22),
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
                                                    decoration: BoxDecoration(
                                                      borderRadius: BorderRadius.circular(18),
                                                    ),
                                                    child: Icon(Icons.keyboard_arrow_down,
                                                        color:
                                                            _totalSearchResults > 0 ? Colors.white70 : Colors.white30,
                                                        size: 22),
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
                                                  decoration: BoxDecoration(
                                                    borderRadius: BorderRadius.circular(16),
                                                  ),
                                                  child: const Icon(Icons.clear, color: Colors.white70, size: 22),
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                      )
                                    : null,
                                filled: true,
                                fillColor: const Color(0xFF1C1C1E).withOpacity(0.95),
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
                                    MixpanelManager().conversationDetailSearchQueryEntered(
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

class SummaryTab extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;

  const SummaryTab({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
  });

  @override
  State<SummaryTab> createState() => _SummaryTabState();
}

class _SummaryTabState extends State<SummaryTab> with AutomaticKeepAliveClientMixin {
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
          behavior: HitTestBehavior.translucent,
          onTap: () {
            FocusScope.of(context).unfocus();
            // If search is empty, call the callback to close search
            if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
              widget.onTapWhenSearchEmpty!();
            }
          },
          child: Selector<ConversationDetailProvider, Tuple3<bool, bool, Function(int)>>(
            selector: (context, provider) =>
                Tuple3(provider.conversation.discarded, provider.showRatingUI, provider.setConversationRating),
            builder: (context, data, child) {
              return Stack(
                children: [
                  ListView(
                    shrinkWrap: true,
                    children: [
                      const GetSummaryWidgets(),
                      data.item1
                          ? const ReprocessDiscardedWidget()
                          : GetAppsWidgets(
                              searchQuery: widget.searchQuery, currentResultIndex: widget.currentResultIndex),
                      const GetGeolocationWidgets(),
                      const SizedBox(height: 150),
                    ],
                  ),
                ],
              );
            },
          ),
        ));
  }
}

class TranscriptWidgets extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;

  const TranscriptWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
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

              return getTranscriptWidget(
                false,
                segments,
                photos,
                null,
                horizontalMargin: false,
                topMargin: false,
                canDisplaySeconds: provider.canDisplaySeconds,
                isConversationDetail: true,
                bottomMargin: 150,
                searchQuery: widget.searchQuery,
                currentResultIndex: widget.currentResultIndex,
                onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
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
                    shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                    ),
                    builder: (context) {
                      return Consumer<PeopleProvider>(builder: (context, peopleProvider, child) {
                        return NameSpeakerBottomSheet(
                          speakerId: speakerId,
                          segmentId: segmentId,
                          segments: provider.conversation.transcriptSegments,
                          onSpeakerAssigned: (speakerId, personId, personName, segmentIds) async {
                            provider.toggleEditSegmentLoading(true);
                            String finalPersonId = personId;
                            if (personId.isEmpty) {
                              Person? newPerson = await peopleProvider.createPersonProvider(personName);
                              if (newPerson != null) {
                                finalPersonId = newPerson.id;
                              } else {
                                provider.toggleEditSegmentLoading(false);
                                return; // Failed to create person
                              }
                            }

                            MixpanelManager().taggedSegment(finalPersonId == 'user' ? 'User' : 'User Person');

                            for (final segmentId in segmentIds) {
                              final segmentIndex =
                                  provider.conversation.transcriptSegments.indexWhere((s) => s.id == segmentId);
                              if (segmentIndex == -1) continue;
                              provider.conversation.transcriptSegments[segmentIndex].isUser = finalPersonId == 'user';
                              provider.conversation.transcriptSegments[segmentIndex].personId =
                                  finalPersonId == 'user' ? null : finalPersonId;
                            }
                            await assignBulkConversationTranscriptSegments(
                              provider.conversation.id,
                              segmentIds,
                              isUser: finalPersonId == 'user',
                              personId: finalPersonId == 'user' ? null : finalPersonId,
                            );
                            provider.toggleEditSegmentLoading(false);
                          },
                        );
                      });
                    },
                  );
                },
              );
            },
          ),
        ));
  }
}

class ActionItemDetailWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;

  const ActionItemDetailWidget({
    super.key,
    required this.actionItem,
    required this.conversationId,
  });

  @override
  State<ActionItemDetailWidget> createState() => _ActionItemDetailWidgetState();
}

class _ActionItemDetailWidgetState extends State<ActionItemDetailWidget> {
  static final Map<String, bool> _pendingStates = {}; // Track pending states by description
  final AppReviewService _appReviewService = AppReviewService();

  @override
  void dispose() {
    // Clean up any pending state for this item when widget is disposed
    _pendingStates.remove(widget.actionItem.description);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        // Find the current action item by description to get the latest state
        final actionItem = provider.conversation.structured.actionItems
            .firstWhere((item) => item.description == widget.actionItem.description, orElse: () => widget.actionItem);

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
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.1),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
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
                                border: Border.all(
                                  color: isCompleted ? Colors.green : Colors.grey,
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: isCompleted
                                  ? const Icon(
                                      Icons.check,
                                      size: 14,
                                      color: Colors.white,
                                    )
                                  : null,
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
      Future.delayed(const Duration(milliseconds: 200), () {
        if (mounted) {
          setState(() {
            _pendingStates.remove(itemDescription); // Clear pending state so item moves to correct section
          });
        }
      });

      // Track analytics - find the current index for analytics
      final currentIndex =
          provider.conversation.structured.actionItems.indexWhere((item) => item.description == itemDescription);
      if (currentIndex != -1) {
        if (newValue) {
          MixpanelManager().checkedActionItem(provider.conversation, currentIndex);

          if (!await _appReviewService.hasCompletedFirstActionItem()) {
            await _appReviewService.markFirstActionItemCompleted();
            _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: false);
          }
        } else {
          MixpanelManager().uncheckedActionItem(provider.conversation, currentIndex);
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
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
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
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.grey[800],
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '${incompleteItems.length}',
                          style: const TextStyle(
                            color: Colors.grey,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
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
              delegate: SliverChildBuilderDelegate(
                (context, index) {
                  final item = incompleteItems[index];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    child: ActionItemDetailWidget(
                      actionItem: item,
                      conversationId: provider.conversation.id,
                    ),
                  );
                },
                childCount: incompleteItems.length,
              ),
            )
          else
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0),
                child: Container(
                  height: 52,
                  decoration: BoxDecoration(
                    color: Colors.grey[900],
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Center(
                    child: Text(
                      'No pending action items',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                      ),
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
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w600,
                            ),
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
                              style: const TextStyle(
                                color: Colors.grey,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
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
              delegate: SliverChildBuilderDelegate(
                (context, index) {
                  final item = completedItems[index];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    child: ActionItemDetailWidget(
                      actionItem: item,
                      conversationId: provider.conversation.id,
                    ),
                  );
                },
                childCount: completedItems.length,
              ),
            )
          else
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0),
                child: Container(
                  height: 52,
                  decoration: BoxDecoration(
                    color: Colors.grey[900],
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Center(
                    child: Text(
                      'No completed items yet',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                      ),
                    ),
                  ),
                ),
              ),
            ),

          const SliverPadding(padding: EdgeInsets.only(bottom: 150)),
        ],
      );
    });
  }

  Widget _buildEmptyState(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.check_circle_outline,
              size: 72,
              color: Colors.grey.shade400,
            ),
            const SizedBox(height: 24),
            Text(
              'No Action Items',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              'Tasks and to-dos from this conversation will appear here once they are created.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 16,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
