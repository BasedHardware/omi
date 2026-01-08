import 'package:flutter/material.dart';
import 'package:omi/widgets/text_selection_controls.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/widgets/extensions/string.dart';

class HumanMessage extends StatelessWidget {
  final ServerMessage message;
  final Function(String)? onAskOmi;

  const HumanMessage({super.key, required this.message, this.onAskOmi});

  @override
  Widget build(BuildContext context) {
    String text = message.text.decodeString;
    String? contextText;
    String messageText = text;

    final contextRegex = RegExp(r'^Context: "([\s\S]+?)"\n\n');
    final match = contextRegex.firstMatch(text);

    if (match != null) {
      contextText = match.group(1);
      messageText = text.substring(match.end);
    }

    return Padding(
      padding: const EdgeInsets.only(left: 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          FilesHandlerWidget(message: message),
          if (contextText != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 6.0, right: 4.0),
              child: Container(
                constraints: const BoxConstraints(maxWidth: 300),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.transparent,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.subdirectory_arrow_right, size: 14, color: Colors.grey),
                    const SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        contextText.length > 50
                            ? '${contextText.substring(0, 50)}...'
                            : contextText,
                        style: TextStyle(
                          color: Colors.grey.shade500,
                          fontSize: 13,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          Wrap(
            alignment: WrapAlignment.end,
            children: [
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1f1f25),
                  borderRadius: BorderRadius.circular(20.0),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                child: SelectableText(
                  messageText.trimRight(),
                  style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
                  contextMenuBuilder: (context, editableTextState) {
                    return omiSelectionMenuBuilder(context, editableTextState, (text) {
                      onAskOmi?.call(text);
                    });
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
