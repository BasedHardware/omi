import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The one grounded follow-up an answer invites, as a single tappable chip.
///
/// Tapping sends the chip's words as a normal user message through the existing
/// chat send path; the chip owns no send logic of its own.
class ChatFollowUpChip extends StatelessWidget {
  const ChatFollowUpChip(
      {super.key, required this.question, required this.onSend, this.source = 'chat_block', this.maxLines = 2});

  final String question;
  final void Function(String) onSend;
  final String source;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        // Match the starter questions above the composer: an outlined action, with no fill.
        child: OutlinedButton(
          key: const Key('chat_followup_chip'),
          style: OutlinedButton.styleFrom(
            foregroundColor: OmiColors.textPrimary,
            minimumSize: const Size(kOmiMinTapTarget, kOmiMinTapTarget),
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            visualDensity: VisualDensity.compact,
            side: BorderSide(color: OmiColors.border),
            shape: const StadiumBorder(),
          ),
          onPressed: () {
            PlatformManager.instance.analytics.followUpChipTapped(source: source);
            onSend(question);
          },
          // Keep generated whitespace from consuming the preview's two lines.
          // Only presentation is shortened; tapping still sends the full question.
          child: MediaQuery.withClampedTextScaling(
            maxScaleFactor: 1.5,
            child: Text(
              question.replaceAll(RegExp(r'\s+'), ' ').trim(),
              style: OmiType.callout,
              textAlign: TextAlign.start,
              maxLines: maxLines,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
      ),
    );
  }
}
