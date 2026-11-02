import 'package:flutter/material.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'conversation_section_sources.dart';
import 'conversation_markdown_widget.dart';

/// First-party notes retain section provenance; editing still addresses the complete summary.
///
/// Each heading is its own row so the section's sources control sits beside it instead of under
/// the prose. The row keeps the 44pt touch target with or without the control, so every heading
/// lines up the same whether or not its section has resolvable sources.
class NoteSectionsSliver extends StatelessWidget {
  final List<Section> sections;
  final List<TranscriptSegment> transcriptSegments;
  final ValueChanged<String>? onOpenSource;
  final VoidCallback? onDoubleTap;

  const NoteSectionsSliver(
      {super.key, required this.sections, required this.transcriptSegments, this.onOpenSource, this.onDoubleTap});

  /// A heading, or a heading-less section whose sources still need a control (it sits right-aligned).
  bool _hasHeaderRow(Section section) =>
      section.heading.trim().isNotEmpty ||
      (onOpenSource != null &&
          ConversationSectionSourcesButton.resolve(section.sourceSegmentIds ?? [], transcriptSegments).isNotEmpty);

  @override
  Widget build(BuildContext context) {
    return SliverMainAxisGroup(slivers: [
      for (var index = 0; index < sections.length; index++) ...[
        if (_hasHeaderRow(sections[index]))
          SliverToBoxAdapter(
            child: Padding(
              // conversationMarkdownHeaderPadding's 26pt above, less the touch target's own slack.
              padding: const EdgeInsets.only(top: 15),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                child: Row(
                  children: [
                    // Double-tap-to-edit wraps only the heading text: a double-tap ancestor would
                    // hold the sources button's single taps in the gesture arena for 300ms.
                    Expanded(
                      child: GestureDetector(
                        behavior: HitTestBehavior.translucent,
                        onDoubleTap: onDoubleTap,
                        child: Semantics(
                          header: true,
                          child: Text(sections[index].heading.trim(), style: OmiType.headline.copyWith(height: 1.3)),
                        ),
                      ),
                    ),
                    if (onOpenSource != null)
                      Transform.translate(
                        // Align the glyph, not the touch target, with the prose's trailing edge.
                        offset: const Offset(OmiSpacing.xs, 0),
                        child: ConversationSectionSourcesButton(
                          key: ValueKey(Object.hash(index, Object.hashAll(sections[index].sourceSegmentIds ?? []))),
                          heading: sections[index].heading,
                          sourceIDs: sections[index].sourceSegmentIds ?? [],
                          transcriptSegments: transcriptSegments,
                          onOpenSource: onOpenSource!,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ConversationMarkdownSliver(content: sections[index].bodyMarkdown, onDoubleTap: onDoubleTap),
        const SliverToBoxAdapter(child: SizedBox(height: OmiSpacing.sm)),
      ],
    ]);
  }
}
