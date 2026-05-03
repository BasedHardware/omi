import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'package:nooto_v2/theme/app_theme.dart';
import 'markdown_style.dart';
import 'models/pie_chart_data.dart';
import 'widgets/accordion_widget.dart';
import 'widgets/bar_chart_widget.dart';
import 'widgets/flow_card.dart';
import 'widgets/highlight_builder.dart';
import 'widgets/highlight_widget.dart';
import 'widgets/in_app_browser.dart';
import 'widgets/pie_chart_widget.dart';
import 'widgets/rich_list_widget.dart';
import 'widgets/story_briefing_card.dart';
import 'widgets/study_card.dart';
import 'widgets/table_card.dart';
import 'widgets/task_card.dart';
import 'xml_parser.dart';

/// Main widget that renders markdown content with embedded generative UI.
class GenerativeMarkdownWidget extends StatelessWidget {
  final String content;
  final void Function(String url)? onUrlTap;
  final bool selectable;

  const GenerativeMarkdownWidget({super.key, required this.content, this.onUrlTap, this.selectable = false});

  @override
  Widget build(BuildContext context) {
    final parser = XmlTagParser();
    final segments = parser.parse(content);

    return DefaultTextStyle(
      style: const TextStyle(
        color: AppColors.textPrimary,
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
      return RichListWidget(items: segment.items, onUrlTap: onUrlTap ?? (url) => InAppBrowser.open(context, url));
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
    return _buildUnsupportedTagPlaceholder(segment);
  }

  /// Defensive fallback for ContentSegment subtypes the renderer doesn't
  /// know how to draw. Per the port contract — silent dropping is not
  /// acceptable. This should be unreachable today (every segment subtype
  /// has a builder) but lives here so adding new segment classes can't
  /// silently break the contract.
  Widget _buildUnsupportedTagPlaceholder(ContentSegment segment) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Container(
        padding: const EdgeInsets.all(AppStyles.spacingM),
        decoration: BoxDecoration(
          color: AppColors.backgroundSecondary,
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        child: Text(
          'Unsupported tag: ${segment.runtimeType}',
          style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
        ),
      ),
    );
  }

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

    var processedContent = markdownContent;

    processedContent = processedContent.replaceAllMapped(
      RegExp(r'<highlight(?:\s+color="([^"]*)")?>([\s\S]*?)</highlight>', caseSensitive: false),
      (match) {
        final color = match.group(1)?.trim().toLowerCase() ?? 'yellow';
        final text = match.group(2)?.trim() ?? '';
        if (text.isEmpty) return '';
        if (text.contains('\n') || text.startsWith('-') || text.startsWith('*') || RegExp(r'^\d+\.').hasMatch(text)) {
          return text;
        }
        return '==$color:$text==';
      },
    );

    processedContent = processedContent.replaceAllMapped(
      RegExp(r'([^\n])\n(---+)(\n|$)'),
      (match) => '${match.group(1)}\n\n${match.group(2)}${match.group(3)}',
    );

    processedContent = processedContent.replaceAllMapped(
      RegExp(r'(^|\n)(#{1,6}\s+[^\n]+)\n(?!\n)'),
      (match) => '${match.group(1)}${match.group(2)}\n\n',
    );

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
            InAppBrowser.open(context, href);
          }
        }
      },
      styleSheet: MarkdownStyleHelper.getStyleSheet(context),
      extensionSet: md.ExtensionSet(md.ExtensionSet.gitHubFlavored.blockSyntaxes, [
        HighlightSyntax(),
        ...md.ExtensionSet.gitHubFlavored.inlineSyntaxes,
      ]),
      builders: {'highlight': HighlightBuilder()},
      data: processedContent,
    );
  }
}
