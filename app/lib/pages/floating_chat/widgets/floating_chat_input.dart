import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:provider/provider.dart';

class FloatingChatInput extends StatefulWidget {
  const FloatingChatInput({super.key});

  @override
  State<FloatingChatInput> createState() => _FloatingChatInputState();
}

class _FloatingChatInputState extends State<FloatingChatInput> {
  final TextEditingController _textController = TextEditingController();

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  void _handleSendPressed() {
    final messageProvider = context.read<MessageProvider>();
    if (_textController.text.isNotEmpty || messageProvider.selectedFiles.isNotEmpty) {
      final text = _textController.text;

      messageProvider.addMessageLocally(text);
      messageProvider.sendMessageStreamToServer(text);

      _textController.clear();
    }
  }

  Widget _buildSelectedFiles(MessageProvider messageProvider) {
    if (messageProvider.selectedFiles.isEmpty) {
      return const SizedBox.shrink();
    }

    return SizedBox(
      height: 50,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.only(left: 8, right: 8, top: 8),
        itemCount: messageProvider.selectedFiles.length,
        itemBuilder: (context, index) {
          final file = messageProvider.selectedFiles[index];
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4.0),
            child: Chip(
              label: Text(
                file.path.split(Platform.pathSeparator).last,
                overflow: TextOverflow.ellipsis,
              ),
              onDeleted: () {
                messageProvider.clearSelectedFile(index);
              },
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final messageProvider = context.watch<MessageProvider>();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildSelectedFiles(messageProvider),
        Padding(
          padding: const EdgeInsets.all(8.0),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.attach_file),
                onPressed: () => messageProvider.selectFile(),
              ),
              Expanded(
                child: TextField(
                  controller: _textController,
                  decoration: const InputDecoration(
                    hintText: 'Type a message...',
                    border: OutlineInputBorder(),
                  ),
                  onSubmitted: (_) => _handleSendPressed(),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.send),
                onPressed: _handleSendPressed,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
