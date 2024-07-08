import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class AddMemoryDialog extends StatefulWidget {
  final Function(Memory) onMemoryAdded;

  const AddMemoryDialog({super.key, required this.onMemoryAdded});

  @override
  _AddMemoryDialogState createState() => _AddMemoryDialogState();
}

class _AddMemoryDialogState extends State<AddMemoryDialog> {
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _descriptionController = TextEditingController();
  final List<TextEditingController> _actionItemControllers = [];

  void _addActionItem() {
    setState(() {
      _actionItemControllers.add(TextEditingController());
    });
  }

  void _removeActionItem(int index) {
    setState(() {
      _actionItemControllers.removeAt(index);
    });
  }

  // void _onSaveButtonPressed() async {
  //   String title = _titleController.text;
  //   String description = _descriptionController.text;
  //   List<String> actionItems = _actionItemControllers.map((controller) => controller.text).toList();
  //   // TODO: create memory
  //   Memory created = await finalizeMemoryRecord(
  //     '',
  //     MemoryStructured(
  //       actionItems: actionItems,
  //       pluginsResponse: [],
  //       title: title,
  //       overview: description,
  //     ),
  //     null,
  //     null,
  //     null,
  //     false,
  //   );
  //   widget.onMemoryAdded(created);
  //   MixpanelManager().manualMemoryCreated(created);
  //   debugPrint('Memory created: ${created.id}');
  //   Navigator.of(context).pop();
  // }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: const BorderSide(
          color: Colors.transparent,
          width: 1,
        ),
      ),
      backgroundColor: const Color(0xFF1E1E1E),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 600),
        decoration: const BoxDecoration(
          borderRadius: BorderRadius.all(Radius.circular(24)),
          border: GradientBoxBorder(
            gradient: LinearGradient(colors: [
              Color.fromARGB(127, 208, 208, 208),
              Color.fromARGB(127, 188, 99, 121),
              Color.fromARGB(127, 86, 101, 182),
              Color.fromARGB(127, 126, 190, 236)
            ]),
            width: 1,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: const BoxDecoration(
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(24),
                  topRight: Radius.circular(24),
                ),
              ),
              child: Text(
                'Add Memory',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Colors.white),
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      decoration: const BoxDecoration(
                        color: Colors.black,
                        borderRadius: BorderRadius.all(Radius.circular(16)),
                        border: GradientBoxBorder(
                          gradient: LinearGradient(colors: [
                            Color.fromARGB(127, 208, 208, 208),
                            Color.fromARGB(127, 188, 99, 121),
                            Color.fromARGB(127, 86, 101, 182),
                            Color.fromARGB(127, 126, 190, 236)
                          ]),
                          width: 1,
                        ),
                        shape: BoxShape.rectangle,
                      ),
                      child: TextField(
                        controller: _titleController,
                        style: const TextStyle(color: Colors.white),
                        decoration: const InputDecoration(
                          labelText: 'Title',
                          labelStyle: TextStyle(color: Colors.white70),
                          border: InputBorder.none,
                          contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      decoration: const BoxDecoration(
                        color: Colors.black,
                        borderRadius: BorderRadius.all(Radius.circular(16)),
                        border: GradientBoxBorder(
                          gradient: LinearGradient(colors: [
                            Color.fromARGB(127, 208, 208, 208),
                            Color.fromARGB(127, 188, 99, 121),
                            Color.fromARGB(127, 86, 101, 182),
                            Color.fromARGB(127, 126, 190, 236)
                          ]),
                          width: 1,
                        ),
                        shape: BoxShape.rectangle,
                      ),
                      child: TextField(
                        controller: _descriptionController,
                        maxLines: 3,
                        style: const TextStyle(color: Colors.white),
                        decoration: const InputDecoration(
                          labelText: 'Overview',
                          alignLabelWithHint: true,
                          labelStyle: TextStyle(color: Colors.white70),
                          border: InputBorder.none,
                          contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Action Items',
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Colors.white),
                    ),
                    const SizedBox(height: 8),
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _actionItemControllers.length,
                      itemBuilder: (context, index) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Row(
                            children: [
                              Expanded(
                                child: Container(
                                  decoration: const BoxDecoration(
                                    color: Colors.black,
                                    borderRadius: BorderRadius.all(Radius.circular(16)),
                                    border: GradientBoxBorder(
                                      gradient: LinearGradient(colors: [
                                        Color.fromARGB(127, 208, 208, 208),
                                        Color.fromARGB(127, 188, 99, 121),
                                        Color.fromARGB(127, 86, 101, 182),
                                        Color.fromARGB(127, 126, 190, 236)
                                      ]),
                                      width: 1,
                                    ),
                                    shape: BoxShape.rectangle,
                                  ),
                                  child: TextField(
                                    controller: _actionItemControllers[index],
                                    style: const TextStyle(color: Colors.white),
                                    decoration: InputDecoration(
                                      hintText: 'Action item ${index + 1}',
                                      hintStyle: const TextStyle(color: Colors.white70),
                                      border: InputBorder.none,
                                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                    ),
                                  ),
                                ),
                              ),
                              if (index > 0)
                                IconButton(
                                  onPressed: () => _removeActionItem(index),
                                  icon: const Icon(Icons.remove_circle_outline, color: Colors.pink),
                                ),
                            ],
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: TextButton.icon(
                onPressed: _addActionItem,
                icon: const Icon(Icons.add, color: Colors.white),
                label: const Text('Add Action Item', style: TextStyle(color: Colors.white)),
              ),
            ),
            const Divider(color: Colors.white24),
            Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel', style: TextStyle(color: Colors.white)),
                  ),
                  const SizedBox(width: 16),
                  ElevatedButton(
                    onPressed: (){},
                    // onPressed: _onSaveButtonPressed,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color.fromARGB(255, 255, 255, 255),
                      foregroundColor: const Color.fromARGB(255, 0, 0, 0),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text('Add'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
