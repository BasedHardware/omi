import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'xml_parser.dart';
import 'models/pie_chart_data.dart';
import 'markdown_style.dart';
import 'widgets/rich_list_widget.dart';
import 'widgets/bar_chart_widget.dart';
import 'widgets/pie_chart_widget.dart';
import 'widgets/accordion_widget.dart';
import 'widgets/story_briefing_card.dart';
import 'widgets/highlight_widget.dart';
import 'widgets/highlight_builder.dart';
import 'widgets/study_card.dart';
import 'widgets/task_card.dart';
import 'widgets/flow_card.dart';
import 'widgets/table_card.dart';
import 'widgets/in_app_browser.dart';

/// Main widget that renders markdown content with embedded generative UI components
class GenerativeMarkdownWidget extends StatelessWidget {
  final String content;
  final Function(String url)? onUrlTap;
  final bool selectable;

  const GenerativeMarkdownWidget({
    super.key,
    required this.content,
    this.onUrlTap,
    this.selectable = false,
  });

  @override
  Widget build(BuildContext context) {
    final parser = XmlTagParser();
    final segments = parser.parse(content);

    // Wrap in DefaultTextStyle to ensure consistent styling
    return DefaultTextStyle(
      style: const TextStyle(
        color: Colors.white,
        fontSize: 16,
        height: 1.5,
        fontStyle: FontStyle.normal,
        fontWeight: FontWeight.normal,
        decoration: TextDecoration.none,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: segments.map((segment) => _buildSegment(context, segment)).toList(),
      ),
    );
  }

  Widget _buildSegment(BuildContext context, ContentSegment segment) {
    if (segment is MarkdownSegment) {
      return _buildMarkdownSegment(context, segment.content);
    } else if (segment is RichListSegment) {
      return RichListWidget(
        items: segment.items,
        onUrlTap: onUrlTap ?? (url) => InAppBrowser.open(context, url),
      );
    } else if (segment is PieChartSegment) {
      return _buildChartWidget(segment.data);
    } else if (segment is AccordionSegment) {
      return GenerativeAccordionWidget(data: segment.data);
    } else if (segment is StoryBriefingSegment) {
      return StoryBriefingCard(data: segment.data);
    } else if (segment is HighlightSegment) {
      return HighlightWidget(data: segment.data);
    } else if (segment is StudySegment) {
      return StudyCard(data: segment.data);
    } else if (segment is TaskSegment) {
      return TaskCard(data: segment.data);
    } else if (segment is FlowSegment) {
      return FlowCard(data: segment.data);
    } else if (segment is TableSegment) {
      return TableCard(data: segment.data);
    }
    return const SizedBox.shrink();
  }

  /// Build the appropriate chart widget based on chart type
  Widget _buildChartWidget(PieChartDisplayData data) {
    if (data.isPieStyle) {
      return GenerativePieChartWidget(data: data);
    }
    return GenerativeBarChartWidget(data: data);
  }

  Widget _buildMarkdownSegment(BuildContext context, String markdownContent) {
    if (markdownContent.trim().isEmpty) {
      return const SizedBox.shrink();
    }

    // Preprocess markdown to fix common formatting issues
    var processedContent = markdownContent;

    // Convert <highlight> tags to custom ==color:text== syntax for inline rendering
    // The HighlightSyntax parser will handle these in the markdown renderer
    // Only convert simple single-line highlights; complex content won't work with inline syntax
    processedContent = processedContent.replaceAllMapped(
      RegExp(r'<highlight(?:\s+color="([^"]*)")?>([\s\S]*?)</highlight>', caseSensitive: false),
      (match) {
        final color = match.group(1)?.trim().toLowerCase() ?? 'yellow';
        final text = match.group(2)?.trim() ?? '';

        // Skip empty highlights
        if (text.isEmpty) return '';

        // For multi-line content or content starting with list markers,
        // just return the text (can't render these as inline highlights)
        if (text.contains('\n') || text.startsWith('-') || text.startsWith('*') || RegExp(r'^\d+\.').hasMatch(text)) {
          return text;
        }

        return '==$color:$text==';
      },
    );

    // Add blank line BEFORE horizontal rules if not present (prevents setext headings)
    // This is critical: text followed directly by --- becomes an H2 heading!
    processedContent = processedContent.replaceAllMapped(
      RegExp(r'([^\n])\n(---+)(\n|$)'),
      (match) => '${match.group(1)}\n\n${match.group(2)}${match.group(3)}',
    );

    // Add blank line after headings if not present (# through ######)
    processedContent = processedContent.replaceAllMapped(
      RegExp(r'(^|\n)(#{1,6}\s+[^\n]+)\n(?!\n)'),
      (match) => '${match.group(1)}${match.group(2)}\n\n',
    );

    // Add blank line after horizontal rules if not present
    processedContent = processedContent.replaceAllMapped(
      RegExp(r'(^|\n)(---+)\n(?!\n)'),
      (match) => '${match.group(1)}${match.group(2)}\n\n',
    );

    return MarkdownBody(
      selectable: selectable,
      shrinkWrap: true,
      onTapLink: (text, href, title) async {
        if (href != null) {
          if (onUrlTap != null) {
            onUrlTap!(href);
          } else {
            // Open in in-app browser by default
            InAppBrowser.open(context, href);
          }
        }
      },
      styleSheet: MarkdownStyleHelper.getStyleSheet(context),
      extensionSet: md.ExtensionSet(
        md.ExtensionSet.gitHubFlavored.blockSyntaxes,
        [
          HighlightSyntax(),
          ...md.ExtensionSet.gitHubFlavored.inlineSyntaxes,
        ],
      ),
      builders: {
        'highlight': HighlightBuilder(),
      },
      data: processedContent,
    );
  }
}
