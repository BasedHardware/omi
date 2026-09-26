import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
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
            borderRadius: OmiRadius.pillAll,
            onTap: () {
              PlatformManager.instance.analytics.followUpChipTapped(source: source);
              onSend(question);
            },
            child: Container(
              // 12 + 19.5pt line + 12 reaches the 44pt target; the min height holds it if the text shrinks.
              constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.sm),
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                borderRadius: OmiRadius.pillAll,
                border: Border.all(color: OmiColors.border),
              ),
              child: Text(question, style: OmiType.subhead.copyWith(height: 1.3)),
            ),
          ),
        ),
      ),
    );
  }
}
