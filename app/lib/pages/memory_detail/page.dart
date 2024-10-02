import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/memory_detail/widgets.dart';
import 'package:friend_private/pages/settings/people.dart';
import 'package:friend_private/pages/settings/recordings_storage_permission.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/services/translation_service.dart';

import 'memory_detail_provider.dart';

class MemoryDetailPage extends StatefulWidget {
  final ServerMemory memory;
  final bool isFromOnboarding;

  const MemoryDetailPage({super.key, this.isFromOnboarding = false, required this.memory});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();

  // TODO: use later for onboarding transcript segment edits
  // late AnimationController _animationController;
  // late Animation<double> _opacityAnimation;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      var provider = Provider.of<MemoryDetailProvider>(context, listen: false);
      await provider.initMemory();
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
        child: MessageListener<MemoryDetailProvider>(
          showError: (error) {
            if (error == 'REPROCESS_FAILED') {
              ScaffoldMessenger.of(context).showSnackBar(
                   SnackBar(content: Text(TranslationService.translate( 'Error while processing memory. Please try again later.'))));
            }
          },
          showInfo: (info) {
            if (info == 'REPROCESS_SUCCESS') {
              ScaffoldMessenger.of(context).showSnackBar(
                 SnackBar(content: Text(TranslationService.translate( 'Memory processed! 🚀'), style: TextStyle(color: Colors.white))),
              );
            }
          },
          child: Scaffold(
            key: scaffoldKey,
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              automaticallyImplyLeading: false,
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
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
                        if (provider.memory.failed) {
                          showDialog(
                            context: context,
                            builder: (c) => getDialog(
                              context,
                              () => Navigator.pop(context),
                              () => Navigator.pop(context),
                            TranslationService.translate( 'Options not available'),
                            TranslationService.translate( 'This memory failed when processing. Options are not available yet, please try again later.'),
                              singleButton: true,
                              okButtonText: 'Ok',
                            ),
                          );
                          return;
                        } else {
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
                        }
                      },
                      icon: const Icon(Icons.more_horiz),
                    ),
                  ],
                );
              }),
            ),
            floatingActionButton: Selector<MemoryDetailProvider, int>(
                selector: (context, provider) => provider.selectedTab,
                builder: (context, selectedTab, child) {
                  return selectedTab == 0
                      ? FloatingActionButton(
                          backgroundColor: Colors.black,
                          elevation: 8,
                          shape: const RoundedRectangleBorder(
                              borderRadius: BorderRadius.all(Radius.circular(32)),
                              side: BorderSide(color: Colors.grey, width: 1)),
                          onPressed: () {
                            var provider = Provider.of<MemoryDetailProvider>(context, listen: false);
                            Clipboard.setData(ClipboardData(text: provider.memory.getTranscript(generate: true)));
                            ScaffoldMessenger.of(context).showSnackBar( SnackBar(
                              content: Text(TranslationService.translate( 'Transcript copied to clipboard')),
                              duration: Duration(seconds: 1),
                            ));
                            MixpanelManager().copiedMemoryDetails(provider.memory, source: 'Transcript');
                          },
                          child: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                        )
                      : const SizedBox.shrink();
                }),
            body: Column(
              children: [
                TabBar(
                  indicatorSize: TabBarIndicatorSize.label,
                  isScrollable: false,
                  onTap: (value) {
                    context.read<MemoryDetailProvider>().updateSelectedTab(value);
                  },
                  padding: EdgeInsets.zero,
                  indicatorPadding: EdgeInsets.zero,
                  labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
                  tabs: [
                    Selector<MemoryDetailProvider, MemorySource?>(
                        selector: (context, provider) => provider.memory.source,
                        builder: (context, memorySource, child) {
                          return Tab(
                            text: memorySource == MemorySource.openglass
                                ? TranslationService.translate( 'Photos')
                                : memorySource == MemorySource.screenpipe
                                    ? TranslationService.translate( 'Raw Data')
                                    : TranslationService.translate( 'Transcript'),
                          );
                        }),
                     Tab(text: TranslationService.translate( 'Summary'))
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
                          Selector<MemoryDetailProvider, MemorySource?>(
                            selector: (context, provider) => provider.memory.source,
                            builder: (context, source, child) {
                              return ListView(
                                shrinkWrap: true,
                                children: source == MemorySource.openglass
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
    return Selector<MemoryDetailProvider, bool>(
      selector: (context, provider) => provider.memory.discarded,
      builder: (context, isDiscaarded, child) {
        return ListView(
          shrinkWrap: true,
          children: [
            const GetSummaryWidgets(),
            isDiscaarded ? const ReprocessDiscardedWidget() : const GetPluginsWidgets(),
            const GetGeolocationWidgets(),
          ],
        );
      },
    );
  }
}

class TranscriptWidgets extends StatelessWidget {
  const TranscriptWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoryDetailProvider>(
      builder: (context, provider, child) {
        return ListView(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            SizedBox(height: provider.memory.transcriptSegments.isEmpty ? 16 : 0),
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
            SizedBox(height: provider.memory.transcriptSegments.isEmpty ? 16 : 0),
            provider.memory.transcriptSegments.isEmpty
                ? ExpandableTextWidget(
                    text: (provider.memory.externalIntegration?.text ?? '').decodeSting,
                    maxLines: 10000,
                    linkColor: Colors.grey.shade300,
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                    toggleExpand: () {
                      provider.toggleIsTranscriptExpanded();
                    },
                    isExpanded: provider.isTranscriptExpanded,
                  )
                : TranscriptWidget(
                    segments: provider.memory.transcriptSegments,
                    horizontalMargin: false,
                    topMargin: false,
                    canDisplaySeconds: provider.canDisplaySeconds,
                    isMemoryDetail: true,
                    editSegment: (_) {},
                    // editSegment: !provider.memory.isPostprocessing()
                    //     ? (i) {
                    //         final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                    //         if (!connectivityProvider.isConnected) {
                    //           ConnectivityProvider.showNoInternetDialog(context);
                    //           return;
                    //         }
                    //         showModalBottomSheet(
                    //           context: context,
                    //           isScrollControlled: true,
                    //           isDismissible: provider.editSegmentLoading ? false : true,
                    //           shape: const RoundedRectangleBorder(
                    //             borderRadius:
                    //                 BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
                    //           ),
                    //           builder: (context) {
                    //             return EditSegmentWidget(
                    //               segmentIdx: i,
                    //               people: SharedPreferencesUtil().cachedPeople,
                    //             );
                    //           },
                    //         );
                    //       }
                    //     : (_) {
                    //         ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    //           content: Text('Memory still processing. Please wait...'),
                    //           duration: Duration(seconds: 1),
                    //         ));
                    //       },
                  ),
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
    return Consumer<MemoryDetailProvider>(builder: (context, provider, child) {
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
                        Text(TranslationService.translate( 'Who\'s segment is this?'), style: Theme.of(context).textTheme.titleLarge),
                        const Spacer(),
                        TextButton(
                          onPressed: () {
                            MixpanelManager().unassignedSegment();
                            provider.unassignMemoryTranscriptSegment(provider.memory.id, segmentIdx);
                            // setModalState(() {
                            //   personId = null;
                            //   isUserSegment = false;
                            // });
                            // setState(() {});
                            Navigator.pop(context);
                          },
                          child:  Text(
                            TranslationService.translate( 'Un-assign'),
                            style: TextStyle(
                              color: Colors.grey,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  !provider.hasAudioRecording ? const SizedBox(height: 12) : const SizedBox(),
                  !provider.hasAudioRecording
                      ? GestureDetector(
                          onTap: () {
                            showDialog(
                              context: context,
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.pop(context),
                                () {
                                  Navigator.pop(context);
                                  routeToPage(context, const RecordingsStoragePermission());
                                },
                              TranslationService.translate( 'Can\'t be used for speech training'),
                            TranslationService.translate( 'This segment can\'t be used for speech training as there is no audio recording available. Check if you have the required permissions for future memories.'),
                                okButtonText: TranslationService.translate( 'View'),
                              ),
                            );
                          },
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                Text(TranslationService.translate( 'Can\'t be used for speech training'),
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodyMedium!
                                        .copyWith(decoration: TextDecoration.underline)),
                                const Padding(
                                  padding: EdgeInsets.only(right: 12),
                                  child: Icon(Icons.info, color: Colors.grey, size: 20),
                                ),
                              ],
                            ),
                          ),
                        )
                      : const SizedBox(),
                  const SizedBox(height: 12),
                  CheckboxListTile(
                    title:  Text(TranslationService.translate( 'Yours')),
                    value: provider.memory.transcriptSegments[segmentIdx].isUser,
                    checkboxShape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                    onChanged: (bool? value) async {
                      if (provider.editSegmentLoading) return;
                      // setModalState(() => loading = true);
                      provider.toggleEditSegmentLoading(true);
                      MixpanelManager().assignedSegment('User');
                      provider.memory.transcriptSegments[segmentIdx].isUser = true;
                      provider.memory.transcriptSegments[segmentIdx].personId = null;
                      bool result = await assignMemoryTranscriptSegment(
                        provider.memory.id,
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
                                  ? TranslationService.translate( 'Segment assigned, and speech profile updated!')
                                  : TranslationService.translate( 'Segment assigned, but speech profile failed to update. Please try again later.')),
                            ),
                          );
                        }
                      } catch (e) {}
                    },
                  ),
                  for (var person in people)
                    CheckboxListTile(
                      title: Text('${person.name}\'s'),
                      value: provider.memory.transcriptSegments[segmentIdx].personId == person.id,
                      checkboxShape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                      onChanged: (bool? value) async {
                        if (provider.editSegmentLoading) return;
                        provider.toggleEditSegmentLoading(true);
                        MixpanelManager().assignedSegment('User Person');
                        provider.memory.transcriptSegments[segmentIdx].isUser = false;
                        provider.memory.transcriptSegments[segmentIdx].personId = person.id;
                        bool result =
                            await assignMemoryTranscriptSegment(provider.memory.id, segmentIdx, personId: person.id);
                        // TODO: make this un-closable or in a way that they receive the result
                        try {
                          provider.toggleEditSegmentLoading(false);
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(result
                                  ? TranslationService.translate( 'Segment assigned, and ${person.name}\'s speech profile updated!')
                                  : TranslationService.translate( 'Segment assigned, but speech profile failed to update. Please try again later.')),
                            ),
                          );
                        } catch (e) {}
                      },
                    ),
                  ListTile(
                    title:  Text(TranslationService.translate( 'Someone else\'s')),
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
