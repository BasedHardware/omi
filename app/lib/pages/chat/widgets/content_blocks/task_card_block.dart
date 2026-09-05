import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Renders a `taskCard` block as a live, toggleable task row.
///
/// The tasks API is list-only (there is no fetch-by-id), so the card resolves
/// against the loaded [ActionItemsProvider] list and mirrors the macOS states:
/// loading while the list is still hydrating, unavailable once it has loaded
/// without the task.
class TaskCardBlock extends StatefulWidget {
  const TaskCardBlock({super.key, required this.block});

  final TaskCardContentBlock block;

  @override
  State<TaskCardBlock> createState() => _TaskCardBlockState();
}

class _TaskCardBlockState extends State<TaskCardBlock> {
  bool _isToggling = false;
  bool _hydrated = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await context.read<ActionItemsProvider>().ensureLoaded();
      if (mounted) setState(() => _hydrated = true);
    });
  }

  ActionItemWithMetadata? _resolve(ActionItemsProvider provider) {
    for (final item in provider.actionItems) {
      if (item.id == widget.block.taskId || item.taskId == widget.block.taskId) return item;
    }
    return null;
  }

  Future<void> _toggle(ActionItemsProvider provider, ActionItemWithMetadata item) async {
    if (_isToggling) return;
    setState(() => _isToggling = true);
    try {
      await provider.updateActionItemState(item, !item.completed);
    } finally {
      if (mounted) setState(() => _isToggling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        final item = _resolve(provider);
        if (item == null) {
          if (!_hydrated || provider.isLoading) {
            return ChatBlockLoading(
              key: Key('chat-block-taskCard-${widget.block.id}-loading'),
              icon: Icons.checklist,
              label: l10n.chatBlockTask,
              message: l10n.loading,
            );
          }
          return ChatBlockUnavailable(
            key: Key('chat-block-taskCard-${widget.block.id}-unavailable'),
            icon: Icons.checklist,
            label: l10n.chatBlockTask,
            message: l10n.chatBlockUnavailable,
          );
        }

        final colorScheme = Theme.of(context).colorScheme;
        return ChatBlockCard(
          key: Key('chat-block-taskCard-${widget.block.id}'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              ChatBlockEyebrow(icon: Icons.checklist, label: l10n.chatBlockTask),
              const SizedBox(height: 6),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  IconButton(
                    key: Key('chat-block-taskCard-${widget.block.id}-toggle'),
                    onPressed: _isToggling ? null : () => _toggle(provider, item),
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                    icon: Icon(
                      item.completed ? Icons.check_circle : Icons.circle_outlined,
                      size: 20,
                      color: item.completed ? Colors.green : colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      item.description,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: item.completed ? colorScheme.onSurfaceVariant : colorScheme.onSurface,
                            decoration: item.completed ? TextDecoration.lineThrough : null,
                          ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
