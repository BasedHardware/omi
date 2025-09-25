import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class ConversationChatInputArea extends StatelessWidget {
  final TextEditingController textController;
  final FocusNode textFieldFocusNode;
  final bool isSending;
  final Function(String) onSendMessage;

  const ConversationChatInputArea({
    super.key,
    required this.textController,
    required this.textFieldFocusNode,
    required this.isSending,
    required this.onSendMessage,
  });

  @override
  Widget build(BuildContext context) {
    // ONE CLEAN STATE - 100% horizontal width
    return Container(
      width: double.infinity, // Force 100% width
      margin: const EdgeInsets.only(top: 10), // Keep small top margin for spacing
      decoration: const BoxDecoration(
        color: Color(0xFF1f1f25),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(22),
          topRight: Radius.circular(22),
        ),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.only(left: 8, right: 8, top: 20, bottom: 20), // Reduced horizontal padding
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                // Main input container - ALWAYS the same
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.only(left: 8, right: 4), // Reduced inner padding for more space
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Expanded(
                          child: Container(
                            alignment: Alignment.centerLeft,
                            child: TextField(
                              enabled: true,
                              controller: textController,
                              focusNode: textFieldFocusNode,
                              obscureText: false,
                              textAlign: TextAlign.start,
                              textAlignVertical: TextAlignVertical.center,
                              decoration: const InputDecoration(
                                hintText: 'Ask about this conversation...',
                                hintStyle: TextStyle(fontSize: 16.0, color: Colors.white54),
                                focusedBorder: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 12),
                                isDense: true,
                              ),
                              minLines: 1,
                              maxLines: 10,
                              keyboardType: TextInputType.multiline,
                              textCapitalization: TextCapitalization.sentences,
                              style: const TextStyle(fontSize: 16.0, color: Colors.white, height: 1.4),
                            ),
                          ),
                        ),

                        // Microphone ALWAYS stays here (never disappears)
                        GestureDetector(
                          child: Container(
                            height: 44,
                            width: 44,
                            alignment: Alignment.center,
                            child: const Icon(
                              FontAwesomeIcons.microphone,
                              color: Colors.white,
                              size: 20,
                            ),
                          ),
                          onTap: () {
                            FocusScope.of(context).unfocus();
                            // TODO: Add voice recording
                          },
                        ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(width: 4), // Minimal gap to maximize space usage

                // Send button - ALWAYS visible (static)
                GestureDetector(
                  onTap: () {
                    HapticFeedback.mediumImpact();
                    String message = textController.text.trim();
                    if (message.isEmpty) return;
                    onSendMessage(message);
                  },
                  child: Container(
                    height: 44,
                    width: 44,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(22),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Icon(
                      FontAwesomeIcons.arrowUp,
                      color: isSending ? Colors.grey[400] : Colors.black,
                      size: 20,
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Smart padding - moves up with keyboard but navbar stays fixed
          SizedBox(
            height: MediaQuery.of(context).padding.bottom + 64 + MediaQuery.of(context).viewInsets.bottom,
          ),
        ],
      ),
    );
  }
}
