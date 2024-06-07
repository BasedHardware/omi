import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

class MemoryDetailPage extends StatefulWidget {
  final dynamic memory;

  const MemoryDetailPage({super.key, this.memory});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();

  late MemoryRecord memory;

  TextEditingController titleController = TextEditingController();
  TextEditingController overviewController = TextEditingController();
  TextEditingController actionItemsController = TextEditingController();
  bool editingTitle = false;
  bool editingOverview = false;

  @override
  void initState() {
    memory = MemoryRecord.fromJson(widget.memory);
    debugPrint(memory.toString());
    titleController.text = memory.structured.title;
    overviewController.text = memory.structured.overview;
    actionItemsController.text = memory.structured.actionItems.join('\n');
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
    return PopScope(
      canPop: false,
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: Theme.of(context).primaryColor,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          backgroundColor: Theme.of(context).primaryColor,
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
              const Text('Memory Detail'),
              Row(
                children: [
                  geyShareMemoryOperationWidget(memory),
                  const SizedBox(width: 16),
                  getDeleteMemoryOperationWidget(memory, null, setState,
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
              SizedBox(height: 24),
              Text(
                '~ ${dateTimeFormat('MMM d, h:mm a', memory.createdAt)}',
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              ),
              SizedBox(height: 12),
              _getFieldHeader('title', focusTitleField),
              _getEditTextField(titleController, editingTitle, focusTitleField),
              _getEditTextFieldButtons(editingTitle, () {
                setState(() {
                  editingTitle = false;
                  titleController.text = memory.structured.title;
                });
              }, () async {
                await MemoryStorage.updateMemory(memory.id, titleController.text, memory.structured.overview);
                memory.structured.title = titleController.text;
                setState(() {
                  editingTitle = false;
                });
                MixpanelManager().memoryEdited(memory, fieldEdited: 'title');
              }),
              SizedBox(height: !memory.discarded ? 32 : 0),
              _getFieldHeader('overview', focusOverviewField),
              _getEditTextField(overviewController, editingOverview, focusOverviewField),
              _getEditTextFieldButtons(editingOverview, () {
                setState(() {
                  editingOverview = false;
                  overviewController.text = memory.structured.overview;
                });
              }, () async {
                await MemoryStorage.updateMemory(memory.id, memory.structured.title, overviewController.text);
                memory.structured.overview = overviewController.text;
                setState(() {
                  editingOverview = false;
                });
                MixpanelManager().memoryEdited(memory, fieldEdited: 'overview');
              }),
              SizedBox(height: !memory.discarded ? 32 : 0),
              memory.structured.actionItems.isNotEmpty
                  ? const Text('Action Items',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600))
                  : const SizedBox.shrink(),
              memory.structured.actionItems.isNotEmpty ? const SizedBox(height: 8) : const SizedBox.shrink(),
              ...memory.structured.actionItems.map<Widget>((item) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 6.0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('-', style: TextStyle(color: Colors.grey.shade200)),
                      const SizedBox(width: 6),
                      Expanded(child: Text(item, style: TextStyle(color: Colors.grey.shade200)))
                    ],
                  ),
                );
              }),
              SizedBox(height: memory.discarded ? 32 : 0),
              if (memory.structured.pluginsResponse.isNotEmpty && !memory.discarded) ...[
                const SizedBox(height: 32),
                const Padding(
                  padding: EdgeInsets.only(left: 4.0),
                  child: Text('Generated by Plugins',
                      style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
                ),
                const SizedBox(height: 16),
                ...memory.structured.pluginsResponse.map((response) => Container(
                      padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: const Color(0x1AF7F4F4),
                        borderRadius: BorderRadius.circular(24.0),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.only(top: 8.0),
                        child: SelectionArea(
                          child: Text(
                            response,
                            style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                          ),
                        ),
                      ),
                    )),
              ],
              const Padding(
                padding: EdgeInsets.only(left: 4.0),
                child: Text('Raw Transcript:',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0x1AF7F4F4),
                  borderRadius: BorderRadius.circular(24.0),
                ),
                child: Padding(
                  padding: const EdgeInsets.only(top: 8.0),
                  child: SelectionArea(
                    child: Text(
                      memory.transcript,
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  _getFieldHeader(String field, FocusNode focusNode) {
    if (memory.discarded) return const SizedBox.shrink();
    String name = '';
    if (field == 'title') {
      name = 'Title';
    } else if (field == 'overview') {
      name = 'Overview';
    }

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(name, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
        Container(
          padding: const EdgeInsetsDirectional.symmetric(horizontal: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                  onPressed: () {
                    setState(() {
                      if (field == 'title') {
                        editingTitle = true;
                      } else if (field == 'overview') {
                        editingOverview = true;
                      }
                    });
                    Timer(const Duration(milliseconds: 100), () => focusNode.requestFocus());
                  },
                  icon: const Icon(Icons.edit, color: Colors.grey, size: 22)),
            ],
          ),
        ),
      ],
    );
  }

  _getEditTextField(TextEditingController controller, bool enabled, FocusNode focusNode) {
    if (memory.discarded) return const SizedBox.shrink();
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

  _getEditTextFieldButtons(bool display, VoidCallback onCanceled, VoidCallback onSaved) {
    return display
        ? Row(
            mainAxisAlignment: MainAxisAlignment.end,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              TextButton(
                onPressed: () {
                  onCanceled();
                },
                child: const Text(
                  'Cancel',
                  style: TextStyle(color: Colors.white),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                  onPressed: () {
                    onSaved();
                  },
                  style: TextButton.styleFrom(
                    textStyle: const TextStyle(color: Colors.white),
                    backgroundColor: Colors.deepPurple,
                  ),
                  child: const Text('Save', style: TextStyle(color: Colors.white))),
            ],
          )
        : const SizedBox.shrink();
  }
}
