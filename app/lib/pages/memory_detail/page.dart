import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memory_detail/share.dart';
import 'package:friend_private/pages/memory_detail/widgets.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/memories/reprocess.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/expandable_text.dart';
import 'package:friend_private/widgets/photos_grid.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:tuple/tuple.dart';

class MemoryDetailPage extends StatefulWidget {
  final ServerMemory memory;

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

  List<MemoryPhoto> photos = [];

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
    }
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

  List<Widget> _getTranscriptWidgets() {
    String decodedRawText = widget.memory.externalIntegration?.text ?? '';
    try {
      decodedRawText = utf8.decode(decodedRawText.codeUnits);
    } catch (e) {}

    return [
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
    StateSetter setModalState,
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
