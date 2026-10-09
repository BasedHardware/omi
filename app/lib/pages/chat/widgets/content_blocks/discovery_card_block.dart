import 'package:flutter/material.dart';

import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Mobile counterpart of the desktop `DiscoveryCard`.
///
/// The block carries a short summary and the full text behind it. Without a
/// component the transcript showed only the synthesized "Discovery - <title> -
/// <summary>" line, which loses the body entirely; this keeps the body one tap
/// away rather than dropping it.
class DiscoveryCardBlock extends StatefulWidget {
  const DiscoveryCardBlock({super.key, required this.block});

  final DiscoveryCardContentBlock block;

  @override
  State<DiscoveryCardBlock> createState() => _DiscoveryCardBlockState();
}

class _DiscoveryCardBlockState extends State<DiscoveryCardBlock> {
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l10n = context.l10n;
    final summary = widget.block.summary.trim();
    final fullText = widget.block.fullText.trim();
    // Expanding is only worth offering when there is more than the summary.
    final hasMore = fullText.isNotEmpty && fullText != summary;
    final body = _isExpanded && hasMore ? fullText : summary;

    return ChatBlockCard(
      onTap: hasMore ? () => setState(() => _isExpanded = !_isExpanded) : null,
      semanticsLabel: '${l10n.discovery}: ${widget.block.title}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: Icons.auto_awesome_outlined, label: l10n.discovery),
          const SizedBox(height: 6),
          if (widget.block.title.trim().isNotEmpty)
            Text(
              widget.block.title,
              style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
          if (body.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(body, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ],
          if (hasMore) ...[
            const SizedBox(height: 8),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _isExpanded ? l10n.chatBlockShowLess : l10n.chatBlockShowMore,
                  style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 2),
                ExcludeSemantics(
                  child: Icon(
                    _isExpanded ? Icons.expand_less : Icons.expand_more,
                    size: 16,
                    color: OmiColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
