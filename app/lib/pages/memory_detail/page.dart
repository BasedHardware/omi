import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/memory_detail/widgets.dart';
import 'package:friend_private/pages/settings/people.dart';
import 'package:friend_private/pages/settings/recordings_storage_permission.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/memories/reprocess.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

class MemoryDetailPage extends StatefulWidget {
  final ServerMemory memory;
  final bool isFromOnboarding;

  const MemoryDetailPage({super.key, required this.memory, this.isFromOnboarding = false});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  final pluginsList = SharedPreferencesUtil().pluginsList;

  late Structured structured;
  TextEditingController titleController = TextEditingController();
  TextEditingController overviewController = TextEditingController();
  bool editingTitle = false;
  bool editingOverview = false;

  List<bool> pluginResponseExpanded = [];
  bool isTranscriptExpanded = false;
  TabController? _controller;

  bool canDisplaySeconds = true;
  bool hasAudioRecording = false;

  List<MemoryPhoto> photos = [];

  // TODO: use later for onboarding transcript segment edits
  // late AnimationController _animationController;
  // late Animation<double> _opacityAnimation;

  @override
  void initState() {
    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(widget.memory.transcriptSegments);
    structured = widget.memory.structured;
    titleController.text = structured.title;
    overviewController.text = structured.overview;
    pluginResponseExpanded = List.filled(widget.memory.pluginsResults.length, false);
    _controller = TabController(length: 2, vsync: this, initialIndex: 1);
    _controller!.addListener(() => setState(() {}));
    if (widget.memory.source == MemorySource.openglass) {
      getMemoryPhotos(widget.memory.id).then((value) {
        photos = value;
        setState(() {}); // TODO: if left before this closes, fails
      });
    } else if (widget.memory.source == MemorySource.friend) {
      hasMemoryRecording(widget.memory.id).then((value) {
        hasAudioRecording = value;
        if (mounted) {
          setState(() {});
        }
      });
    }
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
    titleController.dispose();
    overviewController.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: Row(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              IconButton(
                onPressed: () {
                  if (widget.isFromOnboarding) {
                    SchedulerBinding.instance.addPostFrameCallback((_) {
                      Navigator.pushAndRemoveUntil(
                          context, MaterialPageRoute(builder: (context) => const HomePageWrapper()), (route) => false);
                    });
                  } else {
                    Navigator.pop(context);
                  }
                },
                icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
              ),
              const SizedBox(width: 4),
              Expanded(child: Text("${structured.getEmoji()}")),
              // IconButton(
              //   onPressed: () {
              //     showShareBottomSheet(context, widget.memory, setState);
              //   },
              //   icon: const Icon(Icons.ios_share, size: 20),
              // ),
              IconButton(
                onPressed: () {
                  if (widget.memory.failed) {
                    showDialog(
                        context: context,
                        builder: (c) => getDialog(
                            context,
                            () => Navigator.pop(context),
                            () => Navigator.pop(context),
                            'Options not available',
                            'This memory failed when processing. Options are not available yet, please try again later.',
                            singleButton: true,
                            okButtonText: 'Ok'));
                    return;
                  }
                  showOptionsBottomSheet(context, setState, widget.memory, _reProcessMemory);
                },
                icon: const Icon(Icons.more_horiz),
              ),
            ],
          ),
        ),
        floatingActionButton: _controller!.index == 0
            ? FloatingActionButton(
                backgroundColor: Colors.black,
                elevation: 8,
                shape: const RoundedRectangleBorder(
                    borderRadius: BorderRadius.all(Radius.circular(32)),
                    side: BorderSide(color: Colors.grey, width: 1)),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: widget.memory.getTranscript(generate: true)));
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    content: Text('Transcript copied to clipboard'),
                    duration: Duration(seconds: 1),
                  ));
                  MixpanelManager().copiedMemoryDetails(widget.memory, source: 'Transcript');
                },
                child: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
              )
            : null,
        body: Column(
          children: [
            TabBar(
              indicatorSize: TabBarIndicatorSize.label,
              isScrollable: false,
              padding: EdgeInsets.zero,
              indicatorPadding: EdgeInsets.zero,
              controller: _controller,
              labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
              tabs: [
                Tab(
                  text: widget.memory.source == MemorySource.openglass
                      ? 'Photos'
                      : widget.memory.source == MemorySource.screenpipe
                          ? 'Raw Data'
                          : 'Transcript',
                ),
                const Tab(text: 'Summary')
              ],
              indicator: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(16)),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TabBarView(
                  controller: _controller,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    ListView(
                      shrinkWrap: true,
                      children:
                          widget.memory.source == MemorySource.openglass ? _getImagesWidget() : _getTranscriptWidgets(),
                    ),
                    ListView(
                      shrinkWrap: true,
                      children: getSummaryWidgets(
                            context,
                            widget.memory,
                            overviewController,
                            editingOverview,
                            focusOverviewField,
                            setState,
                          ) +
                          getPluginsWidgets(
                            context,
                            widget.memory,
                            pluginsList,
                            pluginResponseExpanded,
                            (i) => setState(() => pluginResponseExpanded[i] = !pluginResponseExpanded[i]),
                          ) +
                          getGeolocationWidgets(widget.memory, context),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void editSegment(int segmentIdx) {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    List<Person> people = SharedPreferencesUtil().cachedPeople;

    showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.only(topLeft: Radius.circular(16), topRight: Radius.circular(16)),
        ),
        builder: (ctx) {
          bool isUserSegment = widget.memory.transcriptSegments[segmentIdx].isUser;
          String? personId = widget.memory.transcriptSegments[segmentIdx].personId;
          bool loading = false;
          return StatefulBuilder(builder: (BuildContext context, StateSetter setModalState) {
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
                                  widget.memory.transcriptSegments[segmentIdx].isUser = false;
                                  widget.memory.transcriptSegments[segmentIdx].personId = null;
                                  assignMemoryTranscriptSegment(widget.memory.id, segmentIdx);
                                  setModalState(() {
                                    personId = null;
                                    isUserSegment = false;
                                  });
                                  setState(() {});
                                  Navigator.pop(context);
                                },
                                child: const Text('Un-assign',
                                    style: TextStyle(
                                      color: Colors.grey,
                                      decoration: TextDecoration.underline,
                                    )),
                              ),
                            ],
                          ),
                        ),
                        !hasAudioRecording ? const SizedBox(height: 12) : const SizedBox(),
                        !hasAudioRecording
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
                                      'Can\'t be used for speech training',
                                      'This segment can\'t be used for speech training as there is no audio recording available. Check if you have the required permissions for future memories.',
                                      okButtonText: 'View',
                                    ),
                                  );
                                },
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    crossAxisAlignment: CrossAxisAlignment.center,
                                    children: [
                                      Text('Can\'t be used for speech training',
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
                          title: const Text('Yours'),
                          value: isUserSegment,
                          checkboxShape:
                              const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                          onChanged: (bool? value) async {
                            if (loading) return;
                            setModalState(() => loading = true);

                            MixpanelManager().assignedSegment('User');
                            widget.memory.transcriptSegments[segmentIdx].isUser = true;
                            widget.memory.transcriptSegments[segmentIdx].personId = null;
                            bool result = await assignMemoryTranscriptSegment(
                              widget.memory.id,
                              segmentIdx,
                              isUser: true,
                              useForSpeechTraining: SharedPreferencesUtil().hasSpeakerProfile,
                            );
                            try {
                              setModalState(() {
                                personId = null;
                                isUserSegment = true;
                                loading = false;
                              });
                              setState(() {});
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
                            value: personId == person.id,
                            checkboxShape:
                                const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(8))),
                            onChanged: (bool? value) async {
                              if (loading) return;
                              setModalState(() => loading = true);
                              MixpanelManager().assignedSegment('User Person');
                              setState(() {
                                widget.memory.transcriptSegments[segmentIdx].isUser = false;
                                widget.memory.transcriptSegments[segmentIdx].personId = person.id;
                              });
                              bool result = await assignMemoryTranscriptSegment(widget.memory.id, segmentIdx,
                                  personId: person.id);
                              // TODO: make this un-closable or in a way that they receive the result
                              try {
                                setModalState(() {
                                  personId = person.id;
                                  isUserSegment = false;
                                  loading = false;
                                });
                                Navigator.pop(context);
                                setState(() {});
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
                  if (loading)
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
        });
  }

  List<Widget> _getTranscriptWidgets() {
    String decodedRawText = (widget.memory.externalIntegration?.text ?? '').decodeSting;
    bool isPostprocessing = widget.memory.isPostprocessing();
    return [
      SizedBox(height: widget.memory.transcriptSegments.isEmpty ? 16 : 0),
      isPostprocessing
          ? Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.grey.shade800,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text('🚨 Memory still processing. Please wait before reassigning segments.',
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3)),
            )
          : const SizedBox(height: 0),
      SizedBox(height: widget.memory.transcriptSegments.isEmpty ? 16 : 0),
      widget.memory.transcriptSegments.isEmpty
          ? ExpandableTextWidget(
              text: decodedRawText,
              maxLines: 10000,
              linkColor: Colors.grey.shade300,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
              isExpanded: isTranscriptExpanded,
              toggleExpand: () => setState(() => isTranscriptExpanded = !isTranscriptExpanded),
            )
          : TranscriptWidget(
              segments: widget.memory.transcriptSegments,
              horizontalMargin: false,
              topMargin: false,
              canDisplaySeconds: canDisplaySeconds,
              isMemoryDetail: true,
              editSegment: !isPostprocessing
                  ? editSegment
                  : (_) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                        content: Text('Memory still processing. Please wait...'),
                        duration: Duration(seconds: 1),
                      ));
                    },
            ),
      const SizedBox(height: 32)
    ];
  }

  List<Widget> _getImagesWidget() {
    var photosData = photos.map((e) => Tuple2(e.base64, e.description)).toList();
    print('Images length ${photos.length}');
    return [PhotosGridComponent(photos: photosData), const SizedBox(height: 32)];
  }

  _reProcessMemory(
    BuildContext context,
    ServerMemory memory,
    Function changeLoadingState,
  ) async {
    ServerMemory? newMemory = await reProcessMemory(
      context,
      memory,
      () => ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Error while processing memory. Please try again later.'))),
      changeLoadingState,
    );
    if (newMemory == null) return;

    pluginResponseExpanded = List.filled(newMemory.pluginsResults.length, false);
    overviewController.text = newMemory.structured.overview;
    titleController.text = newMemory.structured.title;
    widget.memory.structured.title = newMemory.structured.title;
    widget.memory.structured.overview = newMemory.structured.overview;
    widget.memory.structured.actionItems.clear();
    widget.memory.structured.actionItems.addAll(newMemory.structured.actionItems);
    widget.memory.pluginsResults.clear();
    widget.memory.pluginsResults.addAll(newMemory.pluginsResults);
    widget.memory.discarded = newMemory.discarded;

    SharedPreferencesUtil().modifiedMemoryDetails = widget.memory;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Memory processed! 🚀', style: TextStyle(color: Colors.white))),
    );
    Navigator.pop(context, true);
  }
}
