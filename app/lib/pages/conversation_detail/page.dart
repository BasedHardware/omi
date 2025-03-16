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

  // TODO: use later for onboarding transcript segment edits
  // late AnimationController _animationController;
  // late Animation<double> _opacityAnimation;

  @override
  void initState() {
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
    focusTitleField.dispose();
    focusOverviewField.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: DefaultTabController(
        length: 2,
        initialIndex: 1,
        child: MessageListener<ConversationDetailProvider>(
          showError: (error) {
            if (error == 'REPROCESS_FAILED') {
              ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Error while processing conversation. Please try again later.')));
            }
          },
          showInfo: (info) {
            if (info == 'REPROCESS_SUCCESS') {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Conversation processed! 🚀', style: TextStyle(color: Colors.white))),
              );
            }
          },
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
                    Expanded(child: Text("${provider.structured.getEmoji()}")),
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
            // floatingActionButton: Selector<ConversationDetailProvider, int>(
            //     selector: (context, provider) => provider.selectedTab,
            //     builder: (context, selectedTab, child) {
            //       return selectedTab == 0
            //           ? FloatingActionButton(
            //               backgroundColor: Colors.black,
            //               elevation: 8,
            //               shape: const RoundedRectangleBorder(
            //                   borderRadius: BorderRadius.all(Radius.circular(32)),
            //                   side: BorderSide(color: Colors.grey, width: 1)),
            //               onPressed: () {
            //                 var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
            //                 Clipboard.setData(ClipboardData(text: provider.conversation.getTranscript(generate: true)));
            //                 ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            //                   content: Text('Transcript copied to clipboard'),
            //                   duration: Duration(seconds: 1),
            //                 ));
            //                 MixpanelManager().copiedConversationDetails(provider.conversation, source: 'Transcript');
            //               },
            //               child: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
            //             )
            //           : const SizedBox.shrink();
            //     }),
            body: Stack(
              children: [
                Column(
                  children: [
                    TabBar(
                      indicatorSize: TabBarIndicatorSize.label,
                      isScrollable: false,
                      onTap: (value) {
                        context.read<ConversationDetailProvider>().updateSelectedTab(value);
                      },
                      padding: EdgeInsets.zero,
                      indicatorPadding: EdgeInsets.zero,
                      labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
                      tabs: [
                        Selector<ConversationDetailProvider, ConversationSource?>(
                            selector: (context, provider) => provider.conversation.source,
                            builder: (context, conversationSource, child) {
                              return Tab(
                                text: conversationSource == ConversationSource.openglass
                                    ? 'Photos'
                                    : conversationSource == ConversationSource.screenpipe
                                        ? 'Raw Data'
                                        : 'Transcript',
                              );
                            }),
                        const Tab(text: 'Summary')
                      ],
                      indicator: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(16)),
                    ),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Builder(builder: (context) {
                          return TabBarView(
                            physics: const NeverScrollableScrollPhysics(),
                            children: [
                              Selector<ConversationDetailProvider, ConversationSource?>(
                                selector: (context, provider) => provider.conversation.source,
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
              ],
            ),

            bottomNavigationBar: Container(
              padding: const EdgeInsets.only(left: 30.0, right: 30, bottom: 50, top: 10),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12.0),
                color: Colors.grey.shade900,
                gradient: LinearGradient(
                  colors: [Colors.black54, Colors.black.withOpacity(0)],
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                ),
              ),
              child:
                  Selector<ConversationDetailProvider, ({bool shouldShow, int count})>(selector: (context, provider) {
                return (
                  count: provider.conversation.unassignedSegmentsLength(),
                  shouldShow: provider.showUnassignedFloatingButton && (provider.selectedTab == 0),
                );
              }, builder: (context, value, child) {
                if (value.count == 0 || !value.shouldShow) return const SizedBox.shrink();
                return Material(
                  elevation: 8,
                  borderRadius: BorderRadius.circular(16),
                  color: Colors.grey.shade900,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      vertical: 4,
                      horizontal: 12,
                    ),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(16),
                      color: Colors.grey.shade900,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.3),
                          spreadRadius: 1,
                          blurRadius: 2,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            InkWell(
                              onTap: () {
                                var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
                                provider.setShowUnassignedFloatingButton(false);
                              },
                              child: const Icon(
                                Icons.close,
                                color: Colors.white,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              "${value.count} unassigned segment${value.count == 1 ? '' : 's'}",
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                              ),
                            ),
                          ],
                        ),
                        Row(
                          children: [
                            const SizedBox(width: 8),
                            ElevatedButton(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.white24,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                              ),
                              onPressed: () {
                                var provider = Provider.of<ConversationDetailProvider>(context, listen: false);
                                var speakerId = provider.conversation.speakerWithMostUnassignedSegments();
                                var segmentIdx = provider.conversation.firstSegmentIndexForSpeaker(speakerId);
                                showModalBottomSheet(
                                  context: context,
                                  isScrollControlled: true,
                                  backgroundColor: Colors.black,
                                  shape: const RoundedRectangleBorder(
                                    borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                  ),
                                  builder: (context) {
                                    return NameSpeakerBottomSheet(
                                      segmentIdx: segmentIdx,
                                      speakerId: speakerId,
                                    );
                                  },
                                );
                              },
                              child: const Text(
                                "Tag",
                                style: TextStyle(
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
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
                  const GetGeolocationWidgets(),
                  const SizedBox(height: 120)
                ],
              ),
              data.item2
                  ? Align(
                      alignment: Alignment.bottomLeft,
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.black,
                          shape: BoxShape.rectangle,
                          border: Border.all(color: Colors.grey.shade500),
                          borderRadius: BorderRadius.circular(32),
                        ),
                        padding: const EdgeInsets.all(16),
                        margin: const EdgeInsets.fromLTRB(16, 0, 16, 32),
                        width: 260,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          mainAxisAlignment: MainAxisAlignment.end,
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            const Text(
                              'Was the summary good?',
                              style: TextStyle(fontSize: 18, color: Colors.white, fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(height: 8),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                IconButton(
                                  onPressed: () {
                                    data.item3(0);
                                    AppSnackbar.showSnackbar('Thank you for your feedback!');
                                  },
                                  icon: const Icon(Icons.thumb_down_alt_outlined, size: 30, color: Colors.red),
                                ),
                                const SizedBox(width: 32),
                                IconButton(
                                  onPressed: () {
                                    data.item3(1);
                                    AppSnackbar.showSnackbar('Thank you for your feedback!');
                                  },
                                  icon: const Icon(Icons.thumb_up_alt_outlined, size: 30, color: Colors.green),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink()
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
        return ListView(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            SizedBox(height: provider.conversation.transcriptSegments.isEmpty ? 16 : 0),
            // provider.memory.isPostprocessing()
            //     ? Container(
            //         padding: const EdgeInsets.all(16),
            //         decoration: BoxDecoration(
            //           color: Colors.grey.shade800,
            //           borderRadius: BorderRadius.circular(8),
            //         ),
            //         child: Text('🚨 Memory still processing. Please wait before reassigning segments.',
            //             style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3)),
            //       )
            //     : const SizedBox(height: 0),
            SizedBox(height: provider.conversation.transcriptSegments.isEmpty ? 16 : 0),
            provider.conversation.transcriptSegments.isEmpty
                ? ExpandableTextWidget(
                    text: (provider.conversation.externalIntegration?.text ?? '').decodeString,
                    maxLines: 1000,
                    linkColor: Colors.grey.shade300,
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                    toggleExpand: () {
                      provider.toggleIsTranscriptExpanded();
                    },
                    isExpanded: provider.isTranscriptExpanded,
                  )
                : TranscriptWidget(
                    segments: provider.conversation.transcriptSegments,
                    horizontalMargin: false,
                    topMargin: false,
                    canDisplaySeconds: provider.canDisplaySeconds,
                    isConversationDetail: true,
                    // editSegment: (_) {},
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
                    }),
            const SizedBox(height: 32)
          ],
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
