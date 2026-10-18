import 'package:flutter/material.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'conversation_quote_timestamps.dart';
import 'conversation_markdown_widget.dart';

/// First-party notes retain section provenance; editing still addresses the complete summary.
class NoteSectionsSliver extends StatelessWidget {
  final List<Section> sections;
  final List<TranscriptSegment> transcriptSegments;
  final ValueChanged<String>? onOpenSource;
  final VoidCallback? onDoubleTap;

  const NoteSectionsSliver(
      {super.key, required this.sections, required this.transcriptSegments, this.onOpenSource, this.onDoubleTap});

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
            child: ConversationQuoteTimestamps(
              key: ValueKey(Object.hash(index, Object.hashAll(sections[index].sourceSegmentIds ?? []))),
              sourceIDs: sections[index].sourceSegmentIds ?? [],
              transcriptSegments: transcriptSegments,
              onOpenSource: onOpenSource!,
            ),
          ),
        const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.lg)),
      ],
    ]);
  }
}
