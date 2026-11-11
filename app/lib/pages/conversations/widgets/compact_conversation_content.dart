// Time, title and the existing summary gist for an episode member.
// ConversationListItem retains navigation, locking, selection and deletion.

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/conversation_row_text.dart';
import 'package:omi/ui/ui.dart';

/// Presentation only: ConversationListItem still owns navigation, locking and deletion.
class CompactConversationContent extends StatelessWidget {
  const CompactConversationContent({super.key, required this.conversation, this.overview});
  final ServerConversation conversation;
  final String? overview;

  @override
  Widget build(BuildContext context) {
    final gist = (overview ?? conversation.structured.overview).replaceAll(RegExp(r'\s+'), ' ').trim();
    return Row(
      key: ValueKey('compact_${conversation.id}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: MediaQuery.textScalerOf(context).scale(66),
          child: Text(OmiDateFormat.of(context).time(conversation.startedAt ?? conversation.createdAt),
              maxLines: 1, style: OmiType.footnote.copyWith(height: 1.7, color: OmiColors.textTertiary)),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(conversationRowTitle(context, conversation),
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: OmiType.body),
              if (gist.isNotEmpty) ...[
                const SizedBox(height: OmiSpacing.xxs),
                Text(gist,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              ],
            ],
          ),
        ),
        const SizedBox(width: OmiSpacing.xs),
        Icon(Icons.chevron_right, size: 18, color: OmiColors.textTertiary),
      ],
    );
  }
}
