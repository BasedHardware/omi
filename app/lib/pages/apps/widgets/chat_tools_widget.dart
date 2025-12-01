import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:provider/provider.dart';

class ChatToolsWidget extends StatelessWidget {
  const ChatToolsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(
      builder: (context, provider, child) {
        return Container(
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(12.0),
          ),
          padding: const EdgeInsets.all(14.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Text(
                      'Chat Tools',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () {
                      provider.addChatTool();
                    },
                    icon: const Icon(Icons.add, size: 18, color: Colors.white),
                    label: const Text('Add Tool', style: TextStyle(color: Colors.white)),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (provider.chatTools.isEmpty)
                Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Text(
                    'No chat tools added. Add tools to enable them in Omi chat when users install your app.',
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                  ),
                )
              else
                ...provider.chatTools.asMap().entries.map((entry) {
                  final index = entry.key;
                  final tool = entry.value;
                  return _ChatToolCard(
                    tool: tool,
                    index: index,
                    onDelete: () => provider.removeChatTool(index),
                    onUpdate: (updatedTool) => provider.updateChatTool(index, updatedTool),
                  );
                }).toList(),
            ],
          ),
        );
      },
    );
  }
}

class _ChatToolCard extends StatefulWidget {
  final Map<String, dynamic> tool;
  final int index;
  final VoidCallback onDelete;
  final Function(Map<String, dynamic>) onUpdate;

  const _ChatToolCard({
    required this.tool,
    required this.index,
    required this.onDelete,
    required this.onUpdate,
  });

  @override
  State<_ChatToolCard> createState() => _ChatToolCardState();
}

class _ChatToolCardState extends State<_ChatToolCard> {
  late TextEditingController nameController;
  late TextEditingController descriptionController;
  late TextEditingController endpointController;
  late TextEditingController statusMessageController;
  late String method;
  late bool authRequired;

  @override
  void initState() {
    super.initState();
    nameController = TextEditingController(text: widget.tool['name'] ?? '');
    descriptionController = TextEditingController(text: widget.tool['description'] ?? '');
    endpointController = TextEditingController(text: widget.tool['endpoint'] ?? '');
    statusMessageController = TextEditingController(text: widget.tool['status_message'] ?? '');
    method = widget.tool['method'] ?? 'POST';
    authRequired = widget.tool['auth_required'] ?? true;
    // Defer _updateTool to avoid setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateTool();
    });
  }

  @override
  void dispose() {
    nameController.dispose();
    descriptionController.dispose();
    endpointController.dispose();
    statusMessageController.dispose();
    super.dispose();
  }

  void _updateTool() {
    // Only update if mounted to avoid setState issues
    if (!mounted) return;
    final toolData = {
      'name': nameController.text,
      'description': descriptionController.text,
      'endpoint': endpointController.text,
      'method': method,
      'auth_required': authRequired,
    };
    // Only include status_message if it's not empty
    if (statusMessageController.text.isNotEmpty) {
      toolData['status_message'] = statusMessageController.text;
    }
    widget.onUpdate(toolData);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF2A2A2F),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.shade800),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Tool ${widget.index + 1}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, size: 20, color: Colors.red),
                onPressed: widget.onDelete,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: nameController,
            decoration: InputDecoration(
              labelText: 'Tool Name',
              hintText: 'e.g., send_slack_message',
              labelStyle: TextStyle(color: Colors.grey.shade300),
              hintStyle: TextStyle(color: Colors.grey.shade600),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white),
              ),
            ),
            style: const TextStyle(color: Colors.white),
            onChanged: (_) {
              // Defer to avoid setState during build
              SchedulerBinding.instance.addPostFrameCallback((_) {
                _updateTool();
              });
            },
          ),
          const SizedBox(height: 12),
          TextField(
            controller: descriptionController,
            decoration: InputDecoration(
              labelText: 'Description',
              hintText: 'Describe when and how to use this tool...',
              labelStyle: TextStyle(color: Colors.grey.shade300),
              hintStyle: TextStyle(color: Colors.grey.shade600),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white),
              ),
            ),
            style: const TextStyle(color: Colors.white),
            maxLines: 3,
onChanged: (_) {
              // Defer to avoid setState during build
              SchedulerBinding.instance.addPostFrameCallback((_) {
                _updateTool();
              });
            },
          ),
          const SizedBox(height: 12),
          TextField(
            controller: endpointController,
            decoration: InputDecoration(
              labelText: 'Endpoint URL',
              hintText: 'https://your-server.com/api/tool',
              labelStyle: TextStyle(color: Colors.grey.shade300),
              hintStyle: TextStyle(color: Colors.grey.shade600),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white),
              ),
            ),
            style: const TextStyle(color: Colors.white),
            keyboardType: TextInputType.url,
            onChanged: (_) => _updateTool(),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: statusMessageController,
            decoration: InputDecoration(
              labelText: 'Status Message (Optional)',
              hintText: 'e.g., "Searching Slack", "Sending message"',
              helperText: 'Message shown to users when this tool is called',
              helperMaxLines: 2,
              labelStyle: TextStyle(color: Colors.grey.shade300),
              hintStyle: TextStyle(color: Colors.grey.shade600),
              helperStyle: TextStyle(color: Colors.grey.shade500, fontSize: 12),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: Colors.grey.shade700),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white),
              ),
            ),
            style: const TextStyle(color: Colors.white),
            onChanged: (_) => _updateTool(),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: method,
                  decoration: InputDecoration(
                    labelText: 'HTTP Method',
                    labelStyle: TextStyle(color: Colors.grey.shade300),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: Colors.grey.shade700),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide(color: Colors.grey.shade700),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: const BorderSide(color: Colors.white),
                    ),
                  ),
                  dropdownColor: const Color(0xFF2A2A2F),
                  style: const TextStyle(color: Colors.white),
                  items: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
                      .map((m) => DropdownMenuItem(
                            value: m,
                            child: Text(m),
                          ))
                      .toList(),
                  onChanged: (value) {
                    if (value != null) {
                      setState(() {
                        method = value;
                      });
                      // Defer to avoid setState during build
                      SchedulerBinding.instance.addPostFrameCallback((_) {
                        _updateTool();
                      });
                    }
                  },
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Row(
                  children: [
                    Checkbox(
                      value: authRequired,
                      onChanged: (value) {
                        setState(() {
                          authRequired = value ?? true;
                        });
                        // Defer to avoid setState during build
                        SchedulerBinding.instance.addPostFrameCallback((_) {
                          _updateTool();
                        });
                      },
                      checkColor: Colors.black,
                      fillColor: WidgetStateProperty.resolveWith<Color>(
                        (Set<WidgetState> states) {
                          if (states.contains(WidgetState.selected)) {
                            return Colors.white;
                          }
                          return Colors.transparent;
                        },
                      ),
                    ),
                    Expanded(
                      child: Text(
                        'Auth Required',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
