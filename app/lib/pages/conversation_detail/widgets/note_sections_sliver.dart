import 'package:flutter/material.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'conversation_markdown_widget.dart';

/// First-party notes retain section provenance; editing still addresses the complete summary.
class NoteSectionsSliver extends StatelessWidget {
  final List<Section> sections;
  final ValueChanged<String>? onOpenSource;
  final VoidCallback? onDoubleTap;

  const NoteSectionsSliver({super.key, required this.sections, this.onOpenSource, this.onDoubleTap});

  @override
  Widget build(BuildContext context) {
    return SliverMainAxisGroup(slivers: [
      for (var index = 0; index < sections.length; index++) ...[
        ConversationMarkdownSliver(
          content: sections[index].heading.trim().isEmpty
              ? sections[index].bodyMarkdown
              : '## ${sections[index].heading}\n\n${sections[index].bodyMarkdown}',
          onDoubleTap: onDoubleTap,
        ),
        if (onOpenSource != null && (sections[index].sourceSegmentIds ?? []).isNotEmpty)
          SliverToBoxAdapter(
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Wrap(spacing: OmiSpacing.xs, children: [
                for (var source = 0; source < sections[index].sourceSegmentIds!.length; source++)
                  OmiButton.secondary(
                    key: ValueKey('note-source-$index-$source'),
                    label: '${context.l10n.transcriptTab} ${source + 1}',
                    icon: Icons.format_quote_rounded,
                    size: OmiButtonSize.compact,
                    onPressed: () => onOpenSource!(sections[index].sourceSegmentIds![source]),
                  ),
              ]),
            ),
          ),
        const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.lg)),
      ],
    ]);
  }
}
