import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/memory_detail/share.dart';
import 'package:friend_private/pages/memory_detail/widgets.dart';
import 'package:friend_private/utils/memories/reprocess.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:tuple/tuple.dart';

class MemoryDetailPage extends StatefulWidget {
  final Memory memory;

  const MemoryDetailPage({super.key, required this.memory});

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

  _determineCanDisplaySeconds() {
    var segments = widget.memory.transcriptSegments;
    for (var i = 0; i < segments.length; i++) {
      for (var j = i + 1; j < segments.length; j++) {
        if (segments[i].start > segments[j].end || segments[i].end > segments[j].start) {
          canDisplaySeconds = false;
          break;
        }
      }
    }
  }

  @override
  void initState() {
    _determineCanDisplaySeconds();
    // triggerMemoryCreatedEvents(widget.memory);
    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(widget.memory.transcriptSegments);
    structured = widget.memory.structured.target!;
    titleController.text = structured.title;
    overviewController.text = structured.overview;
    pluginResponseExpanded = List.filled(widget.memory.pluginsResponse.length, false);
    _controller = TabController(length: 2, vsync: this, initialIndex: 1);
    _controller!.addListener(() => setState(() {}));
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
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
              ),
              const SizedBox(width: 4),
              Expanded(child: Text("${structured.getEmoji()}")),
              IconButton(
                onPressed: () {
                  showShareBottomSheet(context, widget.memory, setState);
                },
                icon: const Icon(Icons.ios_share, size: 20),
              ),
              IconButton(
                onPressed: () {
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
                Tab(text: widget.memory.type == MemoryType.image ? 'Photos' : 'Transcript'),
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
                      children: widget.memory.type == MemoryType.image ? _getImagesWidget() : _getTranscriptWidgets(),
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

  List<Widget> _getTranscriptWidgets() {
    return [
      SizedBox(height: widget.memory.transcriptSegments.isEmpty ? 16 : 0),
      widget.memory.transcriptSegments.isEmpty
          ? ExpandableTextWidget(
              text: widget.memory.getTranscript(),
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
              canDisplaySeconds: canDisplaySeconds),
      const SizedBox(height: 32)
    ];
  }

  List<Widget> _getImagesWidget() {
    var photos = widget.memory.photos.map((e) => Tuple2(e.base64, e.description)).toList();
    print('Images length ${photos.length}');
    return [PhotosGridComponent(photos: photos), const SizedBox(height: 32)];
  }

  _reProcessMemory(BuildContext context, StateSetter setModalState, Memory memory, Function changeLoadingState) async {
    Memory? newMemory = await reProcessMemory(
      context,
      memory,
      () => ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Error while processing memory. Please try again later.'))),
      changeLoadingState,
    );

    pluginResponseExpanded = List.filled(memory.pluginsResponse.length, false);
    overviewController.text = newMemory!.structured.target!.overview;
    titleController.text = newMemory.structured.target!.title;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Memory processed! 🚀', style: TextStyle(color: Colors.white))),
    );
    Navigator.pop(context, true);
  }
}
