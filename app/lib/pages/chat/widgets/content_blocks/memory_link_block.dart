import 'dart:async';

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
/// Resolves against the shared memory view and refreshes a missing reference,
/// including when chat saves a memory after the view was loaded. A bounded or
/// failed collection read cannot establish that an individual memory was
/// deleted, so unresolved references keep an explicit retry.
class MemoryLinkBlock extends StatefulWidget {
  const MemoryLinkBlock({super.key, required this.block});

  final MemoryLinkContentBlock block;

  @override
  State<MemoryLinkBlock> createState() => _MemoryLinkBlockState();
}

class _MemoryLinkBlockState extends State<MemoryLinkBlock> {
  bool _hydrating = true;
  int _requestGeneration = 0;

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
      _hydrating = true;
      _scheduleHydration();
    }
  }

  void _scheduleHydration() {
    final generation = ++_requestGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || generation != _requestGeneration) return;
      unawaited(_hydrate(generation, automatic: true));
    });
  }

  Future<void> _hydrate(int generation, {bool automatic = false}) async {
    final provider = context.read<MemoriesProvider>();
    // The provider owns the session-scoped automatic attempt budget and load
    // coalescing. Rebuilding a missing card must not start a polling loop.
    if (_resolve(provider) != null || (automatic && !provider.consumeHydrationAsk(widget.block.memoryId))) {
      if (mounted && generation == _requestGeneration) setState(() => _hydrating = false);
      return;
    }
    setState(() => _hydrating = true);
    try {
      await provider.loadMemories();
    } finally {
      if (mounted && generation == _requestGeneration) setState(() => _hydrating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final memory = _resolve(provider);
        if (memory == null && !_hydrating && !provider.loading) {
          return ChatBlockLinkCard(
            key: Key('chat-block-memoryLink-${widget.block.id}-unresolved'),
            icon: Icons.psychology_outlined,
            label: l10n.chatBlockMemory,
            summary: l10n.couldNotLoadMemories,
            actionTitle: l10n.tryAgain,
            actionKey: Key('chat-block-memoryLink-${widget.block.id}-retry'),
            onAction: () => unawaited(_hydrate(++_requestGeneration)),
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
