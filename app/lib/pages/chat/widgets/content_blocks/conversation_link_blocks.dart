import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart' show resolveChatCitationConversation;
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Opens the conversation behind a `captureLink` / `conversationLink` block.
///
/// Reuses the citation preamble already shipped in chat: resolve from the
/// grouped provider map, fall back to a fetch by id, then push
/// [ConversationDetailPage]. Returns false when the conversation is gone so the
/// caller can show the unavailable state instead of a dead end.
Future<bool> openChatBlockConversation(
  BuildContext context, {
  required String conversationId,
  Future<ServerConversation?> Function(String id)? fetchConversation,
}) async {
  final conversations = Provider.of<ConversationProvider>(context, listen: false);
  final fetch = fetchConversation ?? getConversationById;
  final conversation = await resolveChatCitationConversation(
    conversations: conversations,
    conversationId: conversationId,
    fetchConversation: fetch,
  );
  if (!context.mounted) return false;
  if (conversation == null) return false;

  var located = conversations.getConversationDateAndIndexById(conversation.id);
  var date = located?.$1;
  if (date == null) {
    (_, date) = conversations.addConversationWithDateGrouped(conversation);
  }

  context.read<ConversationDetailProvider>().updateConversation(conversation.id, date);
  await Navigator.of(context).push(
    MaterialPageRoute(builder: (c) => ConversationDetailPage(conversation: conversation)),
  );
  return true;
}

/// Renders a `captureLink` block: a pointer back to the capture that produced
/// the answer.
class CaptureLinkBlock extends StatefulWidget {
  const CaptureLinkBlock({super.key, required this.block, this.fetchConversation});

  final CaptureLinkContentBlock block;
  final Future<ServerConversation?> Function(String id)? fetchConversation;

  @override
  State<CaptureLinkBlock> createState() => _CaptureLinkBlockState();
}

class _CaptureLinkBlockState extends State<CaptureLinkBlock> {
  bool _isOpening = false;
  bool _isUnavailable = false;

  Future<void> _open() async {
    if (_isOpening) return;
    setState(() => _isOpening = true);
    final opened = await openChatBlockConversation(
      context,
      conversationId: widget.block.conversationId,
      fetchConversation: widget.fetchConversation,
    );
    if (!mounted) return;
    setState(() {
      _isOpening = false;
      _isUnavailable = !opened;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (_isUnavailable) {
      return ChatBlockUnavailable(
        key: Key('chat-block-captureLink-${widget.block.id}-unavailable'),
        icon: Icons.graphic_eq,
        label: l10n.chatBlockConversation,
        message: l10n.chatBlockUnavailable,
      );
    }
    return ChatBlockLinkCard(
      key: Key('chat-block-captureLink-${widget.block.id}'),
      icon: Icons.graphic_eq,
      label: l10n.chatBlockConversation,
      summary: widget.block.summary,
      actionTitle: l10n.chatBlockOpenConversation,
      actionKey: Key('chat-block-captureLink-${widget.block.id}-open'),
      isOpening: _isOpening,
      onAction: _open,
    );
  }
}

/// Renders a `conversationLink` block: the conversation plus the action items
/// it recommends. Recommended items are plain rows — mobile creates tasks from
/// the tasks surface, so this block never mutates anything.
class ConversationLinkBlock extends StatefulWidget {
  const ConversationLinkBlock({super.key, required this.block, this.fetchConversation});

  final ConversationLinkContentBlock block;
  final Future<ServerConversation?> Function(String id)? fetchConversation;

  @override
  State<ConversationLinkBlock> createState() => _ConversationLinkBlockState();
}

class _ConversationLinkBlockState extends State<ConversationLinkBlock> {
  bool _isOpening = false;
  bool _isUnavailable = false;

  Future<void> _open() async {
    if (_isOpening) return;
    setState(() => _isOpening = true);
    final opened = await openChatBlockConversation(
      context,
      conversationId: widget.block.conversationId,
      fetchConversation: widget.fetchConversation,
    );
    if (!mounted) return;
    setState(() {
      _isOpening = false;
      _isUnavailable = !opened;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (_isUnavailable) {
      return ChatBlockUnavailable(
        key: Key('chat-block-conversationLink-${widget.block.id}-unavailable'),
        icon: Icons.subject,
        label: l10n.chatBlockConversation,
        message: l10n.chatBlockUnavailable,
      );
    }

    final colorScheme = Theme.of(context).colorScheme;
    final items = widget.block.recommendedActionItems;
    return ChatBlockLinkCard(
      key: Key('chat-block-conversationLink-${widget.block.id}'),
      icon: Icons.subject,
      label: l10n.chatBlockConversation,
      summary: widget.block.summary,
      actionTitle: l10n.chatBlockOpenConversation,
      actionKey: Key('chat-block-conversationLink-${widget.block.id}-open'),
      isOpening: _isOpening,
      onAction: _open,
      footer: items.isEmpty
          ? null
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  l10n.chatBlockRecommendedNextSteps,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(height: 4),
                for (final item in items)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.circle, size: 5, color: colorScheme.onSurfaceVariant),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            item.description,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color: colorScheme.onSurfaceVariant,
                                ),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}
