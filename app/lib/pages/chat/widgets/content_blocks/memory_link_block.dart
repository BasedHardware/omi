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
/// the loaded list renders a loading state while a cold chat asks the provider
/// for its first coalesced load, then becomes unavailable only after that load
/// settles without the row.
class MemoryLinkBlock extends StatefulWidget {
  const MemoryLinkBlock({super.key, required this.block});

  final MemoryLinkContentBlock block;

  @override
  State<MemoryLinkBlock> createState() => _MemoryLinkBlockState();
}

class _MemoryLinkBlockState extends State<MemoryLinkBlock> {
  bool _hydrationRequested = false;

  Memory? _resolve(MemoriesProvider provider) {
    for (final memory in provider.memories) {
      if (memory.id == widget.block.memoryId) return memory;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    _scheduleHydration();
  }

  @override
  void didUpdateWidget(covariant MemoryLinkBlock oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.block.memoryId != widget.block.memoryId) {
      _hydrationRequested = false;
      _scheduleHydration();
    }
  }

  void _scheduleHydration() {
    // Chat can be the first memory surface in a fresh session. Hydrate this
    // shared provider after the first frame so build stays pure; its own
    // coalescing makes simultaneous memory links and the Memories page share
    // one request.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _hydrationRequested) return;
      final provider = context.read<MemoriesProvider>();
      if (provider.hasLoaded) return;
      _hydrationRequested = true;
      provider.loadMemories();
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final memory = _resolve(provider);
        if (memory == null && !provider.loading) {
          return ChatBlockUnavailable(
            key: Key('chat-block-memoryLink-${widget.block.id}-unavailable'),
            icon: Icons.psychology_outlined,
            label: l10n.chatBlockMemory,
            message: l10n.chatBlockUnavailable,
          );
        }

        return ChatBlockLinkCard(
          key: Key('chat-block-memoryLink-${widget.block.id}'),
          icon: Icons.psychology_outlined,
          label: l10n.chatBlockMemory,
          summary: widget.block.summary,
          actionTitle: l10n.chatBlockOpenInMemories,
          actionKey: Key('chat-block-memoryLink-${widget.block.id}-open'),
          isOpening: memory == null,
          onAction: memory == null ? null : () => showMemoryDialog(context, provider, memory: memory),
        );
      },
    );
  }
}
