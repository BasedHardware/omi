import 'package:flutter/material.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/other/temp.dart';

class HumanMessage extends StatelessWidget {
  final ServerMessage message;

  const HumanMessage({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // Padding(
          //   padding: const EdgeInsets.only(right: 8.0, bottom: 4.0),
          //   child: Text(
          //     formatChatTimestamp(message.createdAt),
          //     style: TextStyle(
          //       color: Colors.grey.shade500,
          //       fontSize: 12,
          //     ),
          //   ),
          // ),
          FilesHandlerWidget(message: message),
          Wrap(
            alignment: WrapAlignment.end,
            children: [
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1f1f25),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(16.0),
                    topRight: Radius.circular(16.0),
                    bottomRight: Radius.circular(4.0),
                    bottomLeft: Radius.circular(16.0),
                  ),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                child: Text(
                  message.text.decodeString,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
