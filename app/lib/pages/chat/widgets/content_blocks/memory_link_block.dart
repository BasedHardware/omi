import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/memories/widgets/memory_dialog.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Renders a `memoryLink` block.
///
/// Memories are loaded as a list, so the block resolves the id against
/// [MemoriesProvider] and opens the existing memory sheet. An id that is not in
/// the loaded list renders the unavailable state.
class MemoryLinkBlock extends StatelessWidget {
  const MemoryLinkBlock({super.key, required this.block});

  final MemoryLinkContentBlock block;

  Memory? _resolve(MemoriesProvider provider) {
    for (final memory in provider.memories) {
      if (memory.id == block.memoryId) return memory;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final memory = _resolve(provider);
        if (memory == null && !provider.loading) {
          return ChatBlockUnavailable(
            key: Key('chat-block-memoryLink-${block.id}-unavailable'),
            icon: Icons.psychology_outlined,
            label: l10n.chatBlockMemory,
            message: l10n.chatBlockUnavailable,
          );
        }

        return ChatBlockLinkCard(
          key: Key('chat-block-memoryLink-${block.id}'),
          icon: Icons.psychology_outlined,
          label: l10n.chatBlockMemory,
          summary: block.summary,
          actionTitle: l10n.chatBlockOpenInMemories,
          actionKey: Key('chat-block-memoryLink-${block.id}-open'),
          isOpening: memory == null,
          onAction: memory == null ? null : () => showMemoryDialog(context, provider, memory: memory),
        );
      },
    );
  }
}
