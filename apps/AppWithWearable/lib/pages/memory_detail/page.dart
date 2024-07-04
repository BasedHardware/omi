import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/pages/memories/widgets/confirm_deletion_widget.dart';
import 'package:friend_private/pages/memory_detail/widgets.dart';
import 'package:friend_private/widgets/exapandable_text.dart';
import 'package:friend_private/widgets/transcript.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:share_plus/share_plus.dart';

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
  bool loadingReprocessMemory = false;

  List<bool> pluginResponseExpanded = [];
  bool isTranscriptExpanded = false;
  TabController? _controller;

  @override
  void initState() {
    // devModeWebhookCall(widget.memory);
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
      canPop: false,
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
              Expanded(child: Text(" ${structured.getEmoji()}")),
              const SizedBox(width: 8),
              IconButton(onPressed: _showOptionsBottomSheet, icon: const Icon(Icons.more_horiz)),
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
                  Clipboard.setData(ClipboardData(text: widget.memory.getTranscript()));
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
              tabs: const [Tab(text: 'Transcript'), Tab(text: 'Summary')],
              indicator: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(16)),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: TabBarView(
                  controller: _controller,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    ListView(shrinkWrap: true, children: _getTranscriptWidgets()),
                    ListView(
                        shrinkWrap: true,
                        children: getSummaryWidgets(
                              context,
                              widget.memory,
                              overviewController,
                              editingOverview,
                              focusOverviewField,
                            ) +
                            getPluginsWidgets(
                              context,
                              widget.memory,
                              pluginsList,
                              pluginResponseExpanded,
                              (i) => setState(() => pluginResponseExpanded[i] = !pluginResponseExpanded[i]),
                            )),
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
            ),
      const SizedBox(height: 32)
    ];
  }

  _reProcessMemory(StateSetter setModalState) async {
    debugPrint('_reProcessMemory');
    setModalState(() => loadingReprocessMemory = true);
    MemoryStructured structured;
    try {
      structured = await generateTitleAndSummaryForMemory(widget.memory.transcript, [], forceProcess: true);
    } catch (err, stacktrace) {
      print(err);
      var memoryReporting = MixpanelManager().getMemoryEventProperties(widget.memory);
      CrashReporting.reportHandledCrash(err, stacktrace, level: NonFatalExceptionLevel.critical, userAttributes: {
        'memory_transcript_length': memoryReporting['transcript_length'].toString(),
        'memory_transcript_word_count': memoryReporting['transcript_word_count'].toString(),
        // 'memory_transcript_language': memoryReporting['transcript_language'], // TODO: this is incorrect
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Error while processing memory. Please try again later.'),
        ),
      );
      setModalState(() => loadingReprocessMemory = false);
      return;
    }
    Structured current = widget.memory.structured.target!;
    current.title = structured.title;
    current.overview = structured.overview;
    current.emoji = structured.emoji;
    current.category = structured.category;
    current.actionItems.clear();
    current.actionItems.addAll(structured.actionItems.map<ActionItem>((e) => ActionItem(e)).toList());
    widget.memory.structured.target = current;

    widget.memory.pluginsResponse.clear();
    widget.memory.pluginsResponse.addAll(
      structured.pluginsResponse.map<PluginResponse>((e) => PluginResponse(e.item2, pluginId: e.item1.id)).toList(),
    );

    for (var event in structured.events) {
      current.events.add(CalendarEvent(
        title: event.title,
        description: event.description,
        startsAt: event.startsAt,
        duration: event.duration,
      ));
    }
    pluginResponseExpanded = List.filled(widget.memory.pluginsResponse.length, false);
    widget.memory.discarded = false;
    MemoryProvider().updateMemoryStructured(current);
    MemoryProvider().updateMemory(widget.memory);
    debugPrint('MemoryProvider().updateMemory');
    getEmbeddingsFromInput(structured.toString()).then((vector) {
      createPineconeVector(widget.memory.id.toString(), vector, widget.memory.createdAt);
    });

    overviewController.text = current.overview;
    titleController.text = current.title;

    MixpanelManager().reProcessMemory(widget.memory);

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Memory processed! 🚀', style: TextStyle(color: Colors.white)),
      ),
    );
    debugPrint('Snackbar');
    setModalState(() => loadingReprocessMemory = false);
    Navigator.pop(context, true);
  }

  void _showOptionsBottomSheet() async {
    var result = await showModalBottomSheet(
        context: context,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
          ),
        ),
        builder: (context) => StatefulBuilder(builder: (context, setModalState) {
              return Container(
                height: 216,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(16),
                    topRight: Radius.circular(16),
                  ),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                child: Column(
                  children: [
                    ListTile(
                      title: const Text('Share memory'),
                      leading: const Icon(Icons.send),
                      onTap: loadingReprocessMemory
                          ? null
                          : () {
                              // share loading
                              MixpanelManager().memoryShareButtonClick(widget.memory);
                              Share.share(structured.toString());
                              HapticFeedback.lightImpact();
                            },
                    ),
                    ListTile(
                      title: const Text('Re-summarize'),
                      leading: loadingReprocessMemory
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                              ))
                          : const Icon(Icons.refresh, color: Colors.deepPurple),
                      onTap: loadingReprocessMemory ? null : () => _reProcessMemory(setModalState),
                    ),
                    ListTile(
                      title: const Text('Delete'),
                      leading: const Icon(
                        Icons.delete,
                        color: Colors.red,
                      ),
                      onTap: loadingReprocessMemory
                          ? null
                          : () {
                              showDialog(
                                context: context,
                                builder: (dialogContext) {
                                  return Dialog(
                                    elevation: 0,
                                    insetPadding: EdgeInsets.zero,
                                    backgroundColor: Colors.transparent,
                                    alignment: const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
                                    child: ConfirmDeletionWidget(
                                        memory: widget.memory,
                                        onDelete: () {
                                          Navigator.pop(context, true);
                                          Navigator.pop(context, true);
                                        }),
                                  );
                                },
                              ).then((value) => setState(() {}));
                            },
                    )
                  ],
                ),
              );
            }));
    if (result == true) setState(() {});
    debugPrint('showBottomSheet result: $result');
  }
}
