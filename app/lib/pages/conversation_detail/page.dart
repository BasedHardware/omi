import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

import 'conversation_detail_provider.dart';
import 'widgets/name_speaker_sheet.dart';

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

    _controller = TabController(length: 2, vsync: this, initialIndex: 1); // Start with summary tab
    _controller!.addListener(() {
      setState(() {
        selectedTab = _controller!.index == 0 ? ConversationTab.transcript : ConversationTab.summary;
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      await provider.initConversation();
      if (provider.conversation.appResults.isEmpty) {
        await Provider.of<ConversationProvider>(context, listen: false)
            .updateSearchedConvoDetails(provider.conversation.id, provider.selectedDate, provider.conversationIdx);
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

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: MessageListener<ConversationDetailProvider>(
        showError: (error) {
          if (error == 'REPROCESS_FAILED') {
            ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Error while processing conversation. Please try again later.')));
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
            title: Consumer<ConversationDetailProvider>(builder: (context, provider, child) {
              return Row(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: () {
                      if (widget.isFromOnboarding) {
                        SchedulerBinding.instance.addPostFrameCallback((_) {
                          Navigator.pushAndRemoveUntil(context,
                              MaterialPageRoute(builder: (context) => const HomePageWrapper()), (route) => false);
                        });
                      } else {
                        Navigator.pop(context);
                      }
                    },
                    icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: GestureDetector(
                      onTap: () {
                        if (provider.titleController != null && provider.titleFocusNode != null) {
                          provider.titleFocusNode!.requestFocus();
                          // Select all text in the title field
                          provider.titleController!.selection = TextSelection(
                            baseOffset: 0,
                            extentOffset: provider.titleController!.text.length,
                          );
                        }
                      },
                      child: Text(
                        provider.structured.title,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 18),
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: () async {
                      await showModalBottomSheet(
                        context: context,
                        shape: const RoundedRectangleBorder(
                          borderRadius: BorderRadius.only(
                            topLeft: Radius.circular(16),
                            topRight: Radius.circular(16),
                          ),
                        ),
                        builder: (context) {
                          return const ShowOptionsBottomSheet();
                        },
                      ).whenComplete(() {
                        provider.toggleShareOptionsInSheet(false);
                        provider.toggleDevToolsInSheet(false);
                      });
                    },
                    icon: const Icon(Icons.more_horiz),
                  ),
                ],
              );
            }),
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
                          children: [
                            Selector<ConversationDetailProvider, ConversationSource?>(
                              selector: (context, provider) => provider.conversation?.source,
                              builder: (context, source, child) {
                                return ListView(
                                  shrinkWrap: true,
                                  children: source == ConversationSource.openglass
                                      ? [const PhotosGridComponent(), const SizedBox(height: 32)]
                                      : [const TranscriptWidgets()],
                                );
                              },
                            ),
                            const SummaryTab(),
                          ],
                        );
                      }),
                    ),
                  ),
                ],
              ),

              // Floating bottom bar
              Positioned(
                bottom: 16,
                left: 0,
                right: 0,
                child: Consumer<ConversationDetailProvider>(
                  builder: (context, provider, child) {
                    final conversation = provider.conversation;
                    return ConversationBottomBar(
                      mode: ConversationBottomBarMode.detail,
                      selectedTab: selectedTab,
                      hasSegments: conversation != null && conversation.transcriptSegments.isNotEmpty,
                      onTabSelected: (tab) {
                        int index = tab == ConversationTab.transcript ? 0 : 1;
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
              //          color: Colors.grey.shade900,
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
        selector: (context, provider) =>
            Tuple3(provider.conversation.discarded, provider.showRatingUI, provider.setConversationRating),
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
        final segments = provider.conversation.transcriptSegments;

        if (segments.isEmpty) {
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

        // Use a Container with fixed height for large lists to enable proper scrolling
        return Container(
          height: segments.length > 100 ? MediaQuery.of(context).size.height - 64 : null,
          child: TranscriptWidget(
            segments: segments,
            horizontalMargin: false,
            topMargin: false,
            canDisplaySeconds: provider.canDisplaySeconds,
            isConversationDetail: true,
            bottomMargin: 200,
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
                              content: Text(result
                                  ? 'Segment assigned, and speech profile updated!'
                                  : 'Segment assigned, but speech profile failed to update. Please try again later.'),
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
                        bool result = await assignConversationTranscriptSegment(provider.conversation.id, segmentIdx,
                            personId: person.id);
                        // TODO: make this un-closable or in a way that they receive the result
                        try {
                          provider.toggleEditSegmentLoading(false);
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(result
                                  ? 'Segment assigned, and ${person.name}\'s speech profile updated!'
                                  : 'Segment assigned, but speech profile failed to update. Please try again later.'),
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
