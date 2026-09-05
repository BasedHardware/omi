import 'package:flutter/material.dart';

import 'package:omi/backend/schema/chat_content_block.dart';

import 'chat_block_chrome.dart';

/// Mobile counterparts of the desktop `AgentSpawnCard` / `AgentCompletionCard`.
///
/// A background agent run is started and inspected on the desktop, so these
/// carry no "open" destination the way the goal and memory links do — a phone
/// cannot attach to that session. They are deliberately read-only: the point is
/// that a run the user started still reads as a run in the transcript on their
/// phone, instead of collapsing to the bare line "Agent started - <title>".
class AgentSpawnBlock extends StatelessWidget {
  const AgentSpawnBlock({super.key, required this.block});

  final AgentSpawnContentBlock block;

  @override
  Widget build(BuildContext context) {
    return _AgentRunCard(
      icon: Icons.smart_toy_outlined,
      label: 'Agent started',
      title: block.title,
      body: block.objective,
    );
  }
}

class AgentCompletionBlock extends StatelessWidget {
  const AgentCompletionBlock({super.key, required this.block});

  final AgentCompletionContentBlock block;

  /// The runtime's status vocabulary is open, so anything that is not a known
  /// terminal failure reads as a completed run rather than an invented state.
  bool get _failed {
    final status = block.status.trim().toLowerCase();
    return status == 'failed' || status == 'error' || status == 'cancelled';
  }

  @override
  Widget build(BuildContext context) {
    return _AgentRunCard(
      icon: _failed ? Icons.error_outline : Icons.check_circle_outline,
      label: _failed ? 'Agent stopped' : 'Agent completed',
      title: block.title,
      body: block.output,
    );
  }
}

class _AgentRunCard extends StatelessWidget {
  const _AgentRunCard({
    required this.icon,
    required this.label,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String label;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final trimmedTitle = title.trim();
    final trimmedBody = body.trim();

    return ChatBlockCard(
      semanticsLabel: trimmedTitle.isEmpty ? label : '$label: $trimmedTitle',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: icon, label: label),
          if (trimmedTitle.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(trimmedTitle, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
          ],
          if (trimmedBody.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              trimmedBody,
              maxLines: 6,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
          ],
        ],
      ),
    );
  }
}
