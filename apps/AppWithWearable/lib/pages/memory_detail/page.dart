import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/plugin.dart';
import 'package:friend_private/pages/memories/widgets/confirm_deletion_widget.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:share_plus/share_plus.dart';

class MemoryDetailPage extends StatefulWidget {
  final Memory memory;

  const MemoryDetailPage({super.key, required this.memory});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> {
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

  @override
  void initState() {
    // devModeWebhookCall(widget.memory);
    structured = widget.memory.structured.target!;
    titleController.text = structured.title;
    overviewController.text = structured.overview;
    pluginResponseExpanded = List.filled(widget.memory.pluginsResponse.length, false);
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
    // TODO: include a way to trigger specific plugins
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
                onPressed: () async {
                  Navigator.pop(context);
                },
                icon: const Icon(
                  Icons.arrow_back_rounded,
                  size: 24.0,
                ),
              ),
              Expanded(
                child: Text(
                    " ${structured.getEmoji()} ${widget.memory.discarded ? 'Discarded Memory' : structured.title}"),
              ),
              const SizedBox(width: 8),
              IconButton(
                onPressed: _showOptionsBottomSheet,
                icon: const Icon(Icons.more_horiz),
              ),
            ],
          ),
        ),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: ListView(
            children: [
              const SizedBox(height: 24),
              Text(structured.getEmoji(),
                  style: const TextStyle(color: Colors.white, fontSize: 48, fontWeight: FontWeight.w600)),
              const SizedBox(height: 16),
              Text(
                widget.memory.discarded ? 'Discarded Memory' : structured.title,
                style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 32),
              ),
              const SizedBox(height: 16),
              Table(
                border: TableBorder.all(color: Colors.black),
                columnWidths: const {
                  0: FlexColumnWidth(1),
                  1: FlexColumnWidth(2),
                },
                children: [
                  TableRow(
                    children: [
                      Text(
                        'Created at',
                        style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                      ),
                      Text(
                        dateTimeFormat('MMM d,  yyyy', widget.memory.createdAt),
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ],
                  ),
                  const TableRow(children: [SizedBox(height: 16), SizedBox(height: 16)]),
                  TableRow(children: [
                    Text(
                      widget.memory.startedAt == null ? 'At time' : 'Between',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                    ),
                    Text(
                      widget.memory.startedAt == null
                          ? dateTimeFormat('h:mm a', widget.memory.createdAt)
                          : '${dateTimeFormat('h:mm', widget.memory.startedAt)} to ${dateTimeFormat('h:mm a', widget.memory.finishedAt)}',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ]),
                  TableRow(children: [
                    SizedBox(height: structured.category.isNotEmpty ? 16 : 0),
                    SizedBox(height: structured.category.isNotEmpty ? 16 : 0),
                  ]),
                  structured.category.isNotEmpty
                      ? TableRow(children: [
                          Text(
                            'Category',
                            style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                          ),
                          Text(
                            structured.category[0].toUpperCase() + structured.category.substring(1),
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ])
                      : const TableRow(children: [SizedBox(height: 0), SizedBox(height: 0)]),
                ],
              ),
              const SizedBox(height: 40),
              widget.memory.discarded
                  ? const SizedBox.shrink()
                  : Text(
                      'Overview',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                    ),
              widget.memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
              widget.memory.discarded
                  ? const SizedBox.shrink()
                  : _getEditTextField(overviewController, editingOverview, focusOverviewField),
              widget.memory.discarded ? const SizedBox.shrink() : const SizedBox(height: 40),
              structured.actionItems.isNotEmpty
                  ? Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Action Items',
                          style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                        ),
                        IconButton(
                            onPressed: () {
                              Clipboard.setData(ClipboardData(
                                  text: '- ${structured.actionItems.map((e) => e.description).join('\n- ')}'));
                              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                content: Text('Action items copied to clipboard'),
                                duration: Duration(seconds: 2),
                              ));
                              MixpanelManager().copiedMemoryDetails(widget.memory, source: 'Action Items');
                            },
                            icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20))
                      ],
                    )
                  : const SizedBox.shrink(),
              ...structured.actionItems.map<Widget>((item) {
                return Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 4.0),
                        child:Icon(Icons.task_alt, color: Colors.grey.shade300, size: 20)
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: SelectionArea(
                          child: Text(
                            item.description,
                            style: TextStyle(color: Colors.grey.shade300, fontSize: 16, height: 1.3),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              }),
              structured.actionItems.isNotEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
              if (widget.memory.pluginsResponse.isNotEmpty && !widget.memory.discarded) ...[
                structured.actionItems.isEmpty ? const SizedBox(height: 40) : const SizedBox.shrink(),
                Text(
                  'Plugins 🧑‍💻',
                  style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                ),
                const SizedBox(height: 24),
                ...widget.memory.pluginsResponse.mapIndexed((i, pluginResponse) {
                  if (pluginResponse.content.length < 5) return const SizedBox.shrink();
                  Plugin? plugin = pluginsList.firstWhereOrNull((element) => element.id == pluginResponse.pluginId);
                  return Container(
                    margin: const EdgeInsets.only(bottom: 40),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.start,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        plugin != null
                            ? ListTile(
                                contentPadding: EdgeInsets.zero,
                                leading: CircleAvatar(
                                  backgroundColor: Colors.white,
                                  maxRadius: 16,
                                  backgroundImage: NetworkImage(
                                      'https://raw.githubusercontent.com/BasedHardware/Friend/main/${plugin.image}'),
                                ),
                                title: Text(
                                  plugin.name,
                                  maxLines: 1,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    color: Colors.white,
                                    fontSize: 16,
                                  ),
                                ),
                                subtitle: Padding(
                                  padding: const EdgeInsets.only(top: 4.0),
                                  child: Text(
                                    plugin.description,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(color: Colors.grey, fontSize: 14),
                                  ),
                                ),
                                trailing: IconButton(
                                  icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20),
                                  onPressed: () {
                                    Clipboard.setData(
                                        ClipboardData(text: utf8.decode(pluginResponse.content.trim().codeUnits)));
                                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                      content: Text('Plugin response copied to clipboard'),
                                    ));
                                    MixpanelManager().copiedMemoryDetails(widget.memory, source: 'Plugin Response');
                                  },
                                ),
                              )
                            : const SizedBox.shrink(),
                        ExpandableTextWidget(
                          text: utf8.decode(pluginResponse.content.trim().codeUnits),
                          isExpanded: pluginResponseExpanded[i],
                          toggleExpand: () => setState(() => pluginResponseExpanded[i] = !pluginResponseExpanded[i]),
                          style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                          maxLines: 6,
                          // Change this to 6 if you want the initial max lines to be 6
                          linkColor: Colors.white,
                        ),
                      ],
                    ),
                  );
                }),
              ],
              const SizedBox(height: 8),
              Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text(
                      'Raw Transcript  💬',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                    ),
                    IconButton(
                        onPressed: () {
                          Clipboard.setData(ClipboardData(text: widget.memory.getTranscript()));
                          ScaffoldMessenger.of(context)
                              .showSnackBar(const SnackBar(content: Text('Transcript copied to clipboard')));
                          MixpanelManager().copiedMemoryDetails(widget.memory, source: 'Transcript');
                        },
                        // TODO: improve UI of this copy buttons
                        icon: const Icon(Icons.copy_rounded, color: Colors.white, size: 20))
                  ]),
              const SizedBox(height: 16),
              ExpandableTextWidget(
                text: widget.memory.getTranscript(),
                maxLines: 6,
                linkColor: Colors.grey.shade300,
                style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                isExpanded: isTranscriptExpanded,
                toggleExpand: () => setState(() => isTranscriptExpanded = !isTranscriptExpanded),
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }

  _getEditTextField(TextEditingController controller, bool enabled, FocusNode focusNode) {
    if (widget.memory.discarded) return const SizedBox.shrink();
    return enabled
        ? TextField(
            controller: controller,
            keyboardType: TextInputType.multiline,
            focusNode: focusNode,
            maxLines: null,
            decoration: const InputDecoration(
              border: OutlineInputBorder(borderSide: BorderSide.none),
              contentPadding: EdgeInsets.all(0),
            ),
            enabled: enabled,
            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
          )
        : SelectionArea(
            child: Text(
            controller.text,
            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
          ));
  }

  _reProcessMemory(StateSetter setModalState) async {
    debugPrint('_reProcessMemory');
    setModalState(() => loadingReprocessMemory = true);
    MemoryStructured structured;
    try {
      structured = await generateTitleAndSummaryForMemory(widget.memory.transcript, [], forceProcess: true);
    } catch (err, stacktrace) {
      var memoryReporting = MixpanelManager().getMemoryEventProperties(widget.memory);
      CrashReporting.reportHandledCrash(err, stacktrace, level: NonFatalExceptionLevel.critical, userAttributes: {
        'memory_transcript_length': memoryReporting['transcript_length'].toString(),
        'memory_transcript_word_count': memoryReporting['transcript_word_count'].toString(),
        'memory_transcript_language': memoryReporting['transcript_language'], // TODO: this is incorrect
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
                    ),
                    widget.memory.discarded
                        ? ListTile(
                            title: const Text('Process again and ignore discard.'),
                            leading: loadingReprocessMemory
                                ? const SizedBox(
                                    width: 24,
                                    height: 24,
                                    child: CircularProgressIndicator(
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.deepPurple),
                                    ))
                                : const Icon(Icons.refresh, color: Colors.deepPurple),
                            onTap: loadingReprocessMemory ? null : () => _reProcessMemory(setModalState),
                          )
                        : const SizedBox()
                  ],
                ),
              );
            }));
    if (result == true) setState(() {});
    debugPrint('showBottomSheet result: $result');
  }
}

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final TextStyle style;
  final int maxLines;
  final String expandText;
  final String collapseText;
  final Color linkColor;
  final bool isExpanded;
  final Function toggleExpand;

  const ExpandableTextWidget({
    super.key,
    required this.text,
    required this.style,
    required this.isExpanded,
    required this.toggleExpand,
    this.maxLines = 3,
    this.expandText = 'show more ↓',
    this.collapseText = 'show less ↑',
    this.linkColor = Colors.deepPurple,
  });

  @override
  _ExpandableTextWidgetState createState() => _ExpandableTextWidgetState();
}

class _ExpandableTextWidgetState extends State<ExpandableTextWidget> {
  @override
  Widget build(BuildContext context) {
    final span = TextSpan(text: widget.text, style: widget.style);
    final tp = TextPainter(
      text: span,
      maxLines: widget.maxLines,
      textDirection: TextDirection.ltr,
    );
    tp.layout(maxWidth: MediaQuery.of(context).size.width);
    final isOverflowing = tp.didExceedMaxLines;

    return SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.text,
            style: widget.style,
            maxLines: widget.isExpanded ? 10000 : widget.maxLines,
            overflow: TextOverflow.ellipsis,
          ),
          if (isOverflowing)
            InkWell(
              onTap: () => widget.toggleExpand(),
              child: Padding(
                padding: const EdgeInsets.only(top: 4.0),
                child: Text(
                  widget.isExpanded ? widget.collapseText : widget.expandText,
                  style: TextStyle(
                    color: Colors.deepPurple,
                    fontWeight: FontWeight.w500,
                    fontSize: widget.style.fontSize,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
