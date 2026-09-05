import 'package:flutter/material.dart';

import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';

import 'agent_run_blocks.dart';
import 'conversation_link_blocks.dart';
import 'discovery_card_block.dart';
import 'goal_link_block.dart';
import 'memory_link_block.dart';
import 'question_card_block.dart';
import 'task_card_block.dart';

/// Renders the interactable components for a message's `content_blocks`.
///
/// Every block the desktop transcript draws as its own control has a component
/// here, so a turn reads the same on both clients. text, thinking, toolCall,
/// citation and unknown types are covered by the message body (or its
/// synthesized fallback text) and deliberately render nothing extra — but they
/// never hide the message.
class ChatContentBlockList extends StatelessWidget {
  const ChatContentBlockList({
    super.key,
    required this.message,
    required this.sendMessage,
    this.fetchConversation,
  });

  final ServerMessage message;
  final void Function(String) sendMessage;
  final Future<ServerConversation?> Function(String id)? fetchConversation;

  /// True when at least one block in [message] has an interactable component.
  static bool hasRenderableBlocks(ServerMessage message) {
    return message.typedContentBlocks.any(_isRenderable);
  }

  static bool _isRenderable(ChatContentBlock block) {
    return block is TaskCardContentBlock ||
        block is GoalLinkContentBlock ||
        block is CaptureLinkContentBlock ||
        block is ConversationLinkContentBlock ||
        block is MemoryLinkContentBlock ||
        block is QuestionCardContentBlock ||
        block is DiscoveryCardContentBlock ||
        block is AgentSpawnContentBlock ||
        block is AgentCompletionContentBlock;
  }

  Widget? _build(ChatContentBlock block) {
    switch (block) {
      case TaskCardContentBlock():
        return TaskCardBlock(block: block);
      case GoalLinkContentBlock():
        return GoalLinkBlock(block: block);
      case CaptureLinkContentBlock():
        return CaptureLinkBlock(block: block, fetchConversation: fetchConversation);
      case ConversationLinkContentBlock():
        return ConversationLinkBlock(block: block, fetchConversation: fetchConversation);
      case MemoryLinkContentBlock():
        return MemoryLinkBlock(block: block);
      case QuestionCardContentBlock():
        return QuestionCardBlock(block: block, sendMessage: sendMessage);
      case DiscoveryCardContentBlock():
        return DiscoveryCardBlock(block: block);
      case AgentSpawnContentBlock():
        return AgentSpawnBlock(block: block);
      case AgentCompletionContentBlock():
        return AgentCompletionBlock(block: block);
      case TextContentBlock():
      case ThinkingContentBlock():
      case ToolCallContentBlock():
      case CitationContentBlock():
      case UnknownContentBlock():
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[];
    for (final block in message.typedContentBlocks) {
      final widget = _build(block);
      if (widget == null) continue;
      if (children.isNotEmpty) children.add(const SizedBox(height: 8));
      children.add(widget);
    }
    if (children.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: children,
    );
  }
}
