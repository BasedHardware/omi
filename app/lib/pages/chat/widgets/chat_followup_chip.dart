import 'package:flutter/material.dart';

import 'package:omi/utils/platform/platform_manager.dart';

/// The one grounded follow-up an answer invites, as a single tappable chip.
///
/// Tapping sends the chip's words as a normal user message through the existing
/// chat send path; the chip owns no send logic of its own.
class ChatFollowUpChip extends StatelessWidget {
  const ChatFollowUpChip({super.key, required this.question, required this.onSend, this.source = 'chat_block'});

  final String question;
  final void Function(String) onSend;
  final String source;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Semantics(
          button: true,
          label: question,
          child: InkWell(
            key: const Key('chat_followup_chip'),
            borderRadius: BorderRadius.circular(20),
            onTap: () {
              PlatformManager.instance.analytics.followUpChipTapped(source: source);
              onSend(question);
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
              ),
              child: Text(question, style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.3)),
            ),
          ),
        ),
      ),
    );
  }
}
