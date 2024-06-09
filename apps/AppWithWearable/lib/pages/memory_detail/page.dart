import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';
import 'package:friend_private/utils/temp.dart';

class MemoryDetailPage extends StatefulWidget {
  final MemoryRecord memory;

  const MemoryDetailPage({super.key, required this.memory});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();

  TextEditingController titleController = TextEditingController();
  TextEditingController overviewController = TextEditingController();
  TextEditingController actionItemsController = TextEditingController();
  bool editingTitle = false;
  bool editingOverview = false;

  @override
  void initState() {
    titleController.text = widget.memory.structured.title;
    overviewController.text = widget.memory.structured.overview;
    actionItemsController.text = widget.memory.structured.actionItems.join('\n');
    super.initState();
  }

  @override
  void dispose() {
    titleController.dispose();
    overviewController.dispose();
    actionItemsController.dispose();
    focusTitleField.dispose();
    focusOverviewField.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: scaffoldKey,
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: Theme.of(context).colorScheme.surface,
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
                  " ${widget.memory.structured.emoji} ${widget.memory.discarded ? 'Discarded Memory' : widget.memory.structured.title}"),
            ),
            const SizedBox(width: 8),
            Row(
              // TODO: replace this with new logic here
              children: [
                geyShareMemoryOperationWidget(widget.memory),
                const SizedBox(width: 16),
                getDeleteMemoryOperationWidget(widget.memory, null, setState,
                    iconSize: 24, onDelete: () => Navigator.pop(context, true)),
                const SizedBox(width: 8),
              ],
            )
          ],
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        child: ListView(
          children: [
            const SizedBox(height: 24),
            Text(widget.memory.structured.emoji,
                style: const TextStyle(color: Colors.white, fontSize: 48, fontWeight: FontWeight.w600)),
            const SizedBox(height: 16),
            Text(
              widget.memory.discarded ? 'Discarded Memory' : widget.memory.structured.title,
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
                      'Date Created',
                      style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                    ),
                    Text(
                      dateTimeFormat('MMM d,  yyyy', widget.memory.createdAt),
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ],
                ),
                const TableRow(children: [SizedBox(height: 12), SizedBox(height: 12)]),
                TableRow(children: [
                  Text(
                    'Time Created',
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                  ),
                  Text(
                    dateTimeFormat('h:mm a', widget.memory.createdAt),
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ]),
                TableRow(children: [
                  SizedBox(height: widget.memory.structured.category.isNotEmpty ? 12 : 0),
                  SizedBox(height: widget.memory.structured.category.isNotEmpty ? 12 : 0),
                ]),
                widget.memory.structured.category.isNotEmpty
                    ? TableRow(children: [
                        Text(
                          'Category',
                          style: Theme.of(context).textTheme.titleLarge!.copyWith(color: Colors.grey.shade400),
                        ),
                        Text(
                          widget.memory.structured.category,
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
            widget.memory.discarded
                ? const SizedBox.shrink()
                : const SizedBox(height: 8),
            widget.memory.discarded
                ? const SizedBox.shrink()
                : _getEditTextField(overviewController, editingOverview, focusOverviewField),
            widget.memory.discarded
                ? const SizedBox.shrink()
                : const SizedBox(height: 40),
            widget.memory.structured.actionItems.isNotEmpty
                ? Text(
                    'Action Items',
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
                  )
                : const SizedBox.shrink(),
            widget.memory.structured.actionItems.isNotEmpty ? const SizedBox(height: 8) : const SizedBox.shrink(),
            ...widget.memory.structured.actionItems.map<Widget>((item) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Checkbox(
                      value: false,
                      onChanged: (v) {},
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16.0))),
                  Expanded(
                    child: Text(item, style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3)),
                  ),
                ],
              );
            }),
            if (widget.memory.structured.pluginsResponse.isNotEmpty && !widget.memory.discarded) ...[
              const SizedBox(height: 40),
              Text(
                'Plugins 🧑‍💻',
                style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
              ),
              const SizedBox(height: 24),
              ...widget.memory.structured.pluginsResponse.map((response) => Container(
                    margin: const EdgeInsets.only(bottom: 32),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade900,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: ExpandableTextWidget(
                      text: response.trim(),
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                      maxLines: 6,
                      // Change this to 6 if you want the initial max lines to be 6
                      expandText: 'show more',
                      collapseText: 'show less',
                      linkColor: Colors.white,
                    ),
                  )),
            ],
            const SizedBox(height: 8),
            Text(
              'Raw Transcript  💬',
              style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 26),
            ),
            const SizedBox(height: 16),
            ExpandableTextWidget(
              text: widget.memory.transcript,
              expandText: 'show more',
              collapseText: 'show less',
              maxLines: 3,
              linkColor: Colors.grey.shade300,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  // _getFieldHeader(String field, FocusNode focusNode) {
  //   if (widget.memory.discarded) return const SizedBox.shrink();
  //   String name = '';
  //   if (field == 'title') {
  //     name = 'Title';
  //   } else if (field == 'overview') {
  //     name = 'Overview';
  //   }
  //
  //   return Row(
  //     mainAxisAlignment: MainAxisAlignment.spaceBetween,
  //     children: [
  //       Text(name, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
  //       Container(
  //         padding: const EdgeInsetsDirectional.symmetric(horizontal: 12),
  //         child: Row(
  //           mainAxisSize: MainAxisSize.min,
  //           mainAxisAlignment: MainAxisAlignment.center,
  //           children: [
  //             IconButton(
  //                 onPressed: () {
  //                   setState(() {
  //                     if (field == 'title') {
  //                       editingTitle = true;
  //                     } else if (field == 'overview') {
  //                       editingOverview = true;
  //                     }
  //                   });
  //                   Timer(const Duration(milliseconds: 100), () => focusNode.requestFocus());
  //                 },
  //                 icon: const Icon(Icons.edit, color: Colors.grey, size: 22)),
  //           ],
  //         ),
  //       ),
  //     ],
  //   );
  // }

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

// _getEditTextFieldButtons(bool display, VoidCallback onCanceled, VoidCallback onSaved) {
//   return display
//       ? Row(
//           mainAxisAlignment: MainAxisAlignment.end,
//           crossAxisAlignment: CrossAxisAlignment.center,
//           children: [
//             TextButton(
//               onPressed: () {
//                 onCanceled();
//               },
//               child: const Text(
//                 'Cancel',
//                 style: TextStyle(color: Colors.white),
//               ),
//             ),
//             const SizedBox(width: 8),
//             TextButton(
//                 onPressed: () {
//                   onSaved();
//                 },
//                 style: TextButton.styleFrom(
//                   textStyle: const TextStyle(color: Colors.white),
//                   backgroundColor: Colors.deepPurple,
//                 ),
//                 child: const Text('Save', style: TextStyle(color: Colors.white))),
//           ],
//         )
//       : const SizedBox.shrink();
// }
}

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final TextStyle style;
  final int maxLines;
  final String expandText;
  final String collapseText;
  final Color linkColor;

  ExpandableTextWidget({
    required this.text,
    required this.style,
    this.maxLines = 3,
    this.expandText = 'show more',
    this.collapseText = 'show less',
    this.linkColor = Colors.blue,
  });

  @override
  _ExpandableTextWidgetState createState() => _ExpandableTextWidgetState();
}

class _ExpandableTextWidgetState extends State<ExpandableTextWidget> {
  bool _isExpanded = false;

  void _toggleExpand() {
    setState(() {
      _isExpanded = !_isExpanded;
    });
  }

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
            maxLines: _isExpanded ? 100 : widget.maxLines,
            overflow: TextOverflow.ellipsis,
          ),
          if (isOverflowing)
            InkWell(
              onTap: _toggleExpand,
              child: Padding(
                padding: const EdgeInsets.only(top: 4.0),
                child: Text(
                  _isExpanded ? widget.collapseText : widget.expandText,
                  style: TextStyle(
                    color: widget.linkColor,
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
