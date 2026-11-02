import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Shared visual chrome for chat content-block components.
///
/// Deliberately uses compact link-card paddings, radius, and colors so
/// structured blocks read as one family inside the transcript.
class ChatBlockCard extends StatelessWidget {
  const ChatBlockCard({
    super.key,
    required this.child,
    this.onTap,
    this.semanticsLabel,
    this.explicitChildNodes = false,
  });

  final Widget child;
  final VoidCallback? onTap;
  final String? semanticsLabel;

  /// Keep inner controls (an Undo button) as their own accessibility nodes
  /// instead of folding them into the card's label.
  final bool explicitChildNodes;

  static const BorderRadius radius = OmiRadius.mdAll;

  @override
  Widget build(BuildContext context) {
    final card = Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 10),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: radius,
        border: Border.all(color: OmiColors.border),
      ),
      child: child,
    );

    final content = onTap == null
        ? card
        : InkWell(
            onTap: onTap,
            borderRadius: radius,
            child: card,
          );

    if (semanticsLabel == null) return content;
    return Semantics(
      container: true,
      explicitChildNodes: explicitChildNodes,
      label: semanticsLabel,
      button: onTap != null,
      enabled: onTap != null,
      child: content,
    );
  }
}

/// Small caption row naming the block's entity ("Task", "Goal", ...).
class ChatBlockEyebrow extends StatelessWidget {
  const ChatBlockEyebrow({super.key, required this.icon, required this.label, this.ellipsis = false});

  final IconData icon;
  final String label;

  /// Ellipsize [label] when the row is narrower than the text, as at a large
  /// text scale beside another control.
  final bool ellipsis;

  @override
  Widget build(BuildContext context) {
    final text = Text(
      label,
      maxLines: ellipsis ? 1 : null,
      overflow: ellipsis ? TextOverflow.ellipsis : null,
      style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(child: Icon(icon, size: 14, color: OmiColors.textSecondary)),
        const SizedBox(width: 6),
        if (ellipsis) Flexible(child: text) else text,
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
    return ChatBlockCard(
      semanticsLabel: '$label: $message',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: icon, label: label),
          const SizedBox(height: 6),
          Text(message, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
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
    return ChatBlockCard(
      semanticsLabel: '$label: $message',
      child: Row(
        children: [
          OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textSecondary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
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
            child: OmiButton.tertiary(
              key: actionKey,
              label: actionTitle,
              icon: Icons.open_in_new,
              size: OmiButtonSize.compact,
              isLoading: isOpening,
              onPressed: isOpening ? null : onAction,
            ),
          ),
        ],
      ),
    );
  }
}
