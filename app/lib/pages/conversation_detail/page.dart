import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

import 'conversation_detail_provider.dart';
import 'widgets/name_speaker_sheet.dart';
import '../action_items/widgets/action_item_title_widget.dart';

class ConversationDetailPage extends StatefulWidget {
  final ServerConversation conversation;
  final bool isFromOnboarding;

  const ConversationDetailPage({super.key, this.isFromOnboarding = false, required this.conversation});

  @override
  State<ConversationDetailPage> createState() => _ConversationDetailPageState();
}

class _ConversationDetailPageState extends State<ConversationDetailPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  TabController? _controller;
  ConversationTab selectedTab = ConversationTab.summary;

  // TODO: use later for onboarding transcript segment edits
  // late AnimationController _animationController;
  // late Animation<double> _opacityAnimation;

  @override
  void initState() {
    super.initState();

    _controller = TabController(length: 3, vsync: this, initialIndex: 1); // Start with summary tab
    _controller!.addListener(() {
      setState(() {
        switch (_controller!.index) {
          case 0:
            selectedTab = ConversationTab.transcript;
            break;
          case 1:
            selectedTab = ConversationTab.summary;
            break;
          case 2:
            selectedTab = ConversationTab.actionItems;
            break;
          default:
            debugPrint('Invalid tab index: ${_controller!.index}');
            selectedTab = ConversationTab.summary;
        }
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      var conversationProvider = Provider.of<ConversationProvider>(context, listen: false);

      // Ensure the provider has the conversation data from the widget parameter
      provider.setCachedConversation(widget.conversation);

      // Find the proper date and index for this conversation in the grouped conversations
      var (date, index) = conversationProvider.getConversationDateAndIndex(widget.conversation);
      provider.conversationIdx = index >= 0 ? index : 0;
      provider.selectedDate = date;

      await provider.initConversation();
      if (provider.conversation.appResults.isEmpty) {
        await conversationProvider.updateSearchedConvoDetails(provider.conversation.id, provider.selectedDate, provider.conversationIdx);
        provider.updateConversation(provider.conversationIdx, provider.selectedDate);
      }
    });
    // _animationController = AnimationController(
    //   vsync: this,
    //   duration: const Duration(seconds: 60),
    // )..repeat(reverse: true);
    //
    // _opacityAnimation = Tween<double>(begin: 1.0, end: 0.5).animate(_animationController);

    super.initState();
  }

  @override
  void dispose() {
    _controller?.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    super.dispose();
  }

  String _getTabTitle(ConversationTab tab) {
    switch (tab) {
      case ConversationTab.transcript:
        return 'Transcript';
      case ConversationTab.summary:
        return 'Conversation';
      case ConversationTab.actionItems:
        return 'Action Items';
      default:
        return 'Conversation';
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: MessageListener<ConversationDetailProvider>(
        showError: (error) {
          if (error == 'REPROCESS_FAILED') {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Error while processing conversation. Please try again later.')));
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
                  if (widget.isFromOnboarding) {
                    SchedulerBinding.instance.addPostFrameCallback((_) {
                      Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (context) => const HomePageWrapper()), (route) => false);
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
                  _getTabTitle(selectedTab),
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
                      // Developer Tools button (first)
                      Container(
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: Colors.grey.withOpacity(0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            provider.toggleDevToolsInSheet(true);
                            showModalBottomSheet(
                              context: context,
                              shape: const RoundedRectangleBorder(
                                borderRadius: BorderRadius.only(
                                  topLeft: Radius.circular(16),
                                  topRight: Radius.circular(16),
                                ),
                              ),
                              builder: (context) => const ShowOptionsBottomSheet(),
                            ).whenComplete(() {
                              provider.toggleShareOptionsInSheet(false);
                              provider.toggleDevToolsInSheet(false);
                            });
                          },
                          icon: const FaIcon(FontAwesomeIcons.code, size: 16.0, color: Colors.white),
                        ),
                      ),
                      // Delete button (second)
                      Container(
                        width: 36,
                        height: 36,
                        margin: const EdgeInsets.only(right: 8),
                        decoration: BoxDecoration(
                          color: Colors.grey.withOpacity(0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          onPressed: provider.loadingReprocessConversation
                              ? null
                              : () {
                                  HapticFeedback.mediumImpact();
                                  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                                  if (connectivityProvider.isConnected) {
                                    showDialog(
                                      context: context,
                                      builder: (c) => getDialog(
                                        context,
                                        () => Navigator.pop(context),
                                        () {
                                          context.read<ConversationProvider>().deleteConversation(provider.conversation, provider.conversationIdx);
                                          Navigator.pop(context); // Close dialog
                                          Navigator.pop(context, {'deleted': true}); // Close detail page
                                        },
                                        'Delete Conversation?',
                                        'Are you sure you want to delete this conversation? This action cannot be undone.',
                                        okButtonText: 'Confirm',
                                      ),
                                    );
                                  } else {
                                    showDialog(
                                      context: context,
                                      builder: (c) => getDialog(context, () => Navigator.pop(context), () => Navigator.pop(context), 'Unable to Delete Conversation', 'Please check your internet connection and try again.', singleButton: true, okButtonText: 'OK'),
                                    );
                                  }
                                },
                          icon: const FaIcon(FontAwesomeIcons.trashCan, size: 16.0, color: Colors.white),
                        ),
                      ),
                      // Share button (third)
                      Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: Colors.grey.withOpacity(0.3),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            provider.toggleShareOptionsInSheet(true);
                            showModalBottomSheet(
                              context: context,
                              shape: const RoundedRectangleBorder(
                                borderRadius: BorderRadius.only(
                                  topLeft: Radius.circular(16),
                                  topRight: Radius.circular(16),
                                ),
                              ),
                              builder: (context) => const ShowOptionsBottomSheet(),
                            ).whenComplete(() {
                              provider.toggleShareOptionsInSheet(false);
                              provider.toggleDevToolsInSheet(false);
                            });
                          },
                          icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16.0, color: Colors.white),
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
              Column(
                children: [
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Builder(builder: (context) {
                        return TabBarView(
                          controller: _controller,
                          physics: const NeverScrollableScrollPhysics(),
                          children: const [
                            TranscriptWidgets(),
                            SummaryTab(),
                            ActionItemsTab(),
                          ],
                        );
                      }),
                    ),
                  ),
                ],
              ),

              // Floating bottom bar
              Positioned(
                bottom: 32,
                left: 0,
                right: 0,
                child: Consumer<ConversationDetailProvider>(
                  builder: (context, provider, child) {
                    final conversation = provider.conversation;
                    return ConversationBottomBar(
                      mode: ConversationBottomBarMode.detail,
                      selectedTab: selectedTab,
                      hasSegments: conversation.transcriptSegments.isNotEmpty || conversation.photos.isNotEmpty || conversation.externalIntegration != null,
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
                          default:
                            debugPrint('Invalid tab selected: $tab');
                            index = 1; // Default to summary tab
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
            ],
          ),
        ),
      ),
    );
  }
}

class SummaryTab extends StatelessWidget {
  const SummaryTab({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Selector<ConversationDetailProvider, Tuple3<bool, bool, Function(int)>>(
        selector: (context, provider) => Tuple3(provider.conversation.discarded, provider.showRatingUI, provider.setConversationRating),
        builder: (context, data, child) {
          return Stack(
            children: [
              ListView(
                shrinkWrap: true,
                children: [
                  const GetSummaryWidgets(),
                  data.item1 ? const ReprocessDiscardedWidget() : const GetAppsWidgets(),
                  //const GetGeolocationWidgets(),
                  const SizedBox(height: 150)
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class TranscriptWidgets extends StatelessWidget {
  const TranscriptWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
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

        return Padding(
          padding: const EdgeInsets.only(top: 10),
          child: getTranscriptWidget(
            false,
            segments,
            photos,
            null,
            horizontalMargin: false,
            topMargin: false,
            canDisplaySeconds: provider.canDisplaySeconds,
            isConversationDetail: true,
            bottomMargin: 0, // Removed extra bottom margin
            editSegment: (i, j) {
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
                  return NameSpeakerBottomSheet(
                    speakerId: j,
                    segmentIdx: i,
                  );
                },
              );
            },
          ),
        );
      },
    );
  }
}

class EditSegmentWidget extends StatelessWidget {
  final int segmentIdx;
  final List<Person> people;

  const EditSegmentWidget({super.key, required this.segmentIdx, required this.people});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
      return Container(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: const BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
        ),
        height: 320,
        child: Stack(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
              child: ListView(
                children: [
                  const SizedBox(height: 16),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16.0),
                    child: Row(
                      children: [
                        Text('Who\'s segment is this?', style: Theme.of(context).textTheme.titleLarge),
                        const Spacer(),
                        TextButton(
                          onPressed: () {
                            MixpanelManager().unassignedSegment();
                            provider.unassignConversationTranscriptSegment(provider.conversation.id, segmentIdx);
                            Navigator.pop(context);
                          },
                          child: const Text(
                            'Un-assign',
                            style: TextStyle(
                              color: Colors.grey,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  CheckboxListTile(
                    title: const Text('Yours'),
                    value: provider.conversation.transcriptSegments[segmentIdx].isUser,
                    checkboxShape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                    onChanged: (bool? value) async {
                      if (provider.editSegmentLoading) return;
                      // setModalState(() => loading = true);
                      provider.toggleEditSegmentLoading(true);
                      MixpanelManager().assignedSegment('User');
                      provider.conversation.transcriptSegments[segmentIdx].isUser = true;
                      provider.conversation.transcriptSegments[segmentIdx].personId = null;
                      bool result = await assignConversationTranscriptSegment(
                        provider.conversation.id,
                        segmentIdx,
                        isUser: true,
                        useForSpeechTraining: SharedPreferencesUtil().hasSpeakerProfile,
                      );
                      try {
                        provider.toggleEditSegmentLoading(false);
                        Navigator.pop(context);
                        if (SharedPreferencesUtil().hasSpeakerProfile) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(result ? 'Segment assigned, and speech profile updated!' : 'Segment assigned, but speech profile failed to update. Please try again later.'),
                            ),
                          );
                        }
                      } catch (e) {}
                    },
                  ),
                  for (var person in people)
                    CheckboxListTile(
                      title: Text('${person.name}\'s'),
                      value: provider.conversation.transcriptSegments[segmentIdx].personId == person.id,
                      checkboxShape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                      onChanged: (bool? value) async {
                        if (provider.editSegmentLoading) return;
                        provider.toggleEditSegmentLoading(true);
                        MixpanelManager().assignedSegment('User Person');
                        provider.conversation.transcriptSegments[segmentIdx].isUser = false;
                        provider.conversation.transcriptSegments[segmentIdx].personId = person.id;
                        bool result = await assignConversationTranscriptSegment(provider.conversation.id, segmentIdx, personId: person.id);
                        // TODO: make this un-closable or in a way that they receive the result
                        try {
                          provider.toggleEditSegmentLoading(false);
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(result ? 'Segment assigned, and ${person.name}\'s speech profile updated!' : 'Segment assigned, but speech profile failed to update. Please try again later.'),
                            ),
                          );
                        } catch (e) {}
                      },
                    ),
                  ListTile(
                    title: const Text('Someone else\'s'),
                    trailing: const Padding(
                      padding: EdgeInsets.only(right: 8),
                      child: Icon(Icons.add),
                    ),
                    onTap: () {
                      Navigator.pop(context);
                      routeToPage(context, const UserPeoplePage());
                    },
                  ),
                ],
              ),
            ),
            if (provider.editSegmentLoading)
              Container(
                color: Colors.black.withOpacity(0.3),
                child: const Center(
                    child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation(Colors.white),
                )),
              ),
          ],
        ),
      );
    });
  }
}

class ActionItemDetailWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;
  final int itemIndexInConversation;

  const ActionItemDetailWidget({
    super.key,
    required this.actionItem,
    required this.conversationId,
    required this.itemIndexInConversation,
  });

  @override
  State<ActionItemDetailWidget> createState() => _ActionItemDetailWidgetState();
}

class _ActionItemDetailWidgetState extends State<ActionItemDetailWidget> {
  bool _isAnimating = false;
  bool? _localCompletionState; // Local state for immediate visual feedback

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final actionItem = provider.conversation.structured.actionItems[widget.itemIndexInConversation];

        // Use local state if available, otherwise use the provider state
        final isCompleted = _localCompletionState ?? actionItem.completed;

        return AnimatedOpacity(
          opacity: _isAnimating ? 0.7 : 1.0,
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

    // Update local state immediately for instant visual feedback
    setState(() {
      _localCompletionState = newValue;
      _isAnimating = true;
    });

    // Get ConversationProvider for global state management
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);

    try {
      // Update global state immediately (this handles server + provider state)
      await conversationProvider.updateGlobalActionItemState(provider.conversation, widget.itemIndexInConversation, newValue);

      // Wait for 1 second before clearing local state (which will show the item in correct section)
      Future.delayed(const Duration(milliseconds: 500), () {
        if (mounted) {
          // Clear local state so item shows in correct section
          setState(() {
            _localCompletionState = null;
            _isAnimating = false;
          });
        }
      });

      // Track analytics
      if (newValue) {
        MixpanelManager().checkedActionItem(provider.conversation, widget.itemIndexInConversation);
      } else {
        MixpanelManager().uncheckedActionItem(provider.conversation, widget.itemIndexInConversation);
      }
    } catch (e) {
      // If there's an error, revert local state
      if (mounted) {
        setState(() {
          _localCompletionState = null;
          _isAnimating = false;
        });
      }
      debugPrint('Error updating action item state: $e');
    }
  }
}

class ActionItemsTab extends StatelessWidget {
  const ActionItemsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Consumer<ConversationDetailProvider>(
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
                      final itemIndex = provider.conversation.structured.actionItems.indexOf(item);
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        child: ActionItemDetailWidget(
                          actionItem: item,
                          conversationId: provider.conversation.id,
                          itemIndexInConversation: itemIndex,
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
                      final itemIndex = provider.conversation.structured.actionItems.indexOf(item);
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                        child: ActionItemDetailWidget(
                          actionItem: item,
                          conversationId: provider.conversation.id,
                          itemIndexInConversation: itemIndex,
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
        },
      ),
    );
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
