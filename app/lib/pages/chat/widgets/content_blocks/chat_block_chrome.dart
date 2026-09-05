import 'package:flutter/material.dart';

/// Shared visual chrome for chat content-block components.
///
/// Deliberately mirrors [ChatEvidenceReferenceCard]'s paddings, radius, and
/// colors so structured blocks read as one family inside the transcript.
class ChatBlockCard extends StatelessWidget {
  const ChatBlockCard({
    super.key,
    required this.child,
    this.onTap,
    this.semanticsLabel,
  });

  final Widget child;
  final VoidCallback? onTap;
  final String? semanticsLabel;

  static const double radius = 10;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final card = Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.55)),
      ),
      child: child,
    );

    final content = onTap == null
        ? card
        : InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(radius),
            child: card,
          );

    if (semanticsLabel == null) return content;
    return Semantics(
      container: true,
      label: semanticsLabel,
      button: onTap != null,
      enabled: onTap != null,
      child: content,
    );
  }
}

/// Small caption row naming the block's entity ("Task", "Goal", ...).
class ChatBlockEyebrow extends StatelessWidget {
  const ChatBlockEyebrow({super.key, required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: colorScheme.onSurfaceVariant),
        const SizedBox(width: 6),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w600,
              ),
        ),
      ],
    );
  }
}

/// Terminal state for a block whose entity cannot be resolved any more.
class ChatBlockUnavailable extends StatelessWidget {
  const ChatBlockUnavailable({
    super.key,
    required this.icon,
    required this.label,
    required this.message,
  });

  final IconData icon;
  final String label;
  final String message;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ChatBlockCard(
      semanticsLabel: '$label: $message',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: icon, label: label),
          const SizedBox(height: 6),
          Text(
            message,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

/// Placeholder while the owning store is still hydrating the entity.
class ChatBlockLoading extends StatelessWidget {
  const ChatBlockLoading({
    super.key,
    required this.icon,
    required this.label,
    required this.message,
  });

  final IconData icon;
  final String label;
  final String message;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ChatBlockCard(
      semanticsLabel: '$label: $message',
      child: Row(
        children: [
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: colorScheme.onSurfaceVariant),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

/// Summary + single destination action, shared by the goal/capture/conversation
/// /memory link blocks.
class ChatBlockLinkCard extends StatelessWidget {
  const ChatBlockLinkCard({
    super.key,
    required this.icon,
    required this.label,
    required this.summary,
    required this.actionTitle,
    required this.actionKey,
    required this.onAction,
    this.isOpening = false,
    this.footer,
  });

  final IconData icon;
  final String label;
  final String summary;
  final String actionTitle;
  final Key actionKey;
  final VoidCallback? onAction;
  final bool isOpening;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ChatBlockCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: icon, label: label),
          const SizedBox(height: 6),
          Text(summary, style: Theme.of(context).textTheme.bodyMedium),
          if (footer != null) ...[const SizedBox(height: 8), footer!],
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: actionKey,
              onPressed: isOpening ? null : onAction,
              icon: isOpening
                  ? SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(strokeWidth: 2, color: colorScheme.onSurfaceVariant),
                    )
                  : const Icon(Icons.open_in_new, size: 16),
              label: Text(actionTitle),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: const Size(0, 32),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                foregroundColor: colorScheme.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
