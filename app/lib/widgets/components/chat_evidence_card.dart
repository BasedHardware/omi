import 'package:flutter/material.dart';

import 'package:omi/models/chat_evidence_reference.dart';

/// Supplemental evidence chrome for a chat answer.
///
/// This widget intentionally owns no answer text and never throws for an
/// unavailable reference. Callers can render it beside the normal text bubble;
/// loading, offline, pruned, and failed evidence therefore cannot block or
/// replace the answer itself.
class ChatEvidenceReferenceCard extends StatelessWidget {
  const ChatEvidenceReferenceCard({
    super.key,
    required this.reference,
    this.onOpen,
  });

  final ChatEvidenceReference reference;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final canOpen = reference.canOpen && onOpen != null;
    final colorScheme = Theme.of(context).colorScheme;
    final borderColor = reference.state == ChatEvidenceReferenceState.available
        ? colorScheme.outline.withValues(alpha: 0.55)
        : colorScheme.outline.withValues(alpha: 0.3);
    final card = Container(
      key: ValueKey('chat-evidence-${reference.id}'),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            _iconFor(reference),
            size: 18,
            color: colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  reference.title?.trim().isNotEmpty == true ? reference.title! : reference.sourceLabel,
                ),
                const SizedBox(height: 2),
                Text(
                  reference.summary?.trim().isNotEmpty == true ? reference.summary! : reference.statusLabel,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
            ),
          ),
          if (canOpen) ...[
            const SizedBox(width: 8),
            Icon(
              Icons.open_in_new,
              size: 16,
              color: colorScheme.onSurfaceVariant,
            ),
          ],
        ],
      ),
    );

    return Semantics(
      container: true,
      label: reference.accessibilityLabel,
      button: canOpen,
      enabled: canOpen,
      hint: canOpen ? 'Open evidence' : null,
      child: canOpen
          ? InkWell(
              onTap: onOpen,
              borderRadius: BorderRadius.circular(10),
              child: card,
            )
          : card,
    );
  }

  static IconData _iconFor(ChatEvidenceReference reference) {
    switch (reference.kind) {
      case ChatEvidenceReferenceKind.conversationSummary:
        return Icons.subject;
      case ChatEvidenceReferenceKind.conversationSegment:
        return Icons.short_text;
      case ChatEvidenceReferenceKind.screen:
        return Icons.desktop_windows_outlined;
      case ChatEvidenceReferenceKind.keyframe:
        return Icons.image_outlined;
      case ChatEvidenceReferenceKind.request:
      case ChatEvidenceReferenceKind.unknown:
        return Icons.link;
    }
  }
}

class ChatEvidenceReferenceList extends StatelessWidget {
  const ChatEvidenceReferenceList({
    super.key,
    required this.envelope,
    this.onOpen,
  });

  final ChatEvidenceReferenceEnvelope envelope;
  final void Function(ChatEvidenceReference reference)? onOpen;

  @override
  Widget build(BuildContext context) {
    if (envelope.isEmpty) return const SizedBox.shrink();
    return Column(
      key: const ValueKey('chat-evidence-reference-list'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var index = 0; index < envelope.references.length; index++) ...[
          if (index > 0) const SizedBox(height: 8),
          ChatEvidenceReferenceCard(
            reference: envelope.references[index],
            onOpen: onOpen == null ? null : () => onOpen!(envelope.references[index]),
          ),
        ],
      ],
    );
  }
}
