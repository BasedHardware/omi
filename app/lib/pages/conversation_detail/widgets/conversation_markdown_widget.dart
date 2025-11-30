import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'package:omi/widgets/generative_ui/generative_ui.dart';

class ConversationMarkdownWidget extends StatefulWidget {
  final String content;
  final String searchQuery;
  final int currentResultIndex;
  final Function(ScrollController)? onScrollControllerReady;

  const ConversationMarkdownWidget({
    super.key,
    required this.content,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onScrollControllerReady,
  });

  @override
  State<ConversationMarkdownWidget> createState() => _ConversationMarkdownWidgetState();
}

class _ConversationMarkdownWidgetState extends State<ConversationMarkdownWidget> {
  final ScrollController _scrollController = ScrollController();
  final List<GlobalKey> _paragraphKeys = [];
  int _previousSearchResultIndex = -1;

  List<String> _paragraphs = [];

  @override
  void initState() {
    super.initState();
    _initializeParagraphs();
    widget.onScrollControllerReady?.call(_scrollController);
  }

  @override
  void didUpdateWidget(ConversationMarkdownWidget oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (widget.content != oldWidget.content) {
      _initializeParagraphs();
    }

    if (widget.currentResultIndex != _previousSearchResultIndex &&
        widget.currentResultIndex >= 0 &&
        widget.searchQuery.isNotEmpty) {
      _previousSearchResultIndex = widget.currentResultIndex;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToSearchResult();
      });
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _initializeParagraphs() {
    _paragraphs = widget.content.split('\n').where((p) => p.trim().isNotEmpty).toList();
    _paragraphKeys.clear();
    _paragraphKeys.addAll(List.generate(_paragraphs.length, (index) => GlobalKey()));
  }

  // Calculate which paragraph contains the current search result
  int _findParagraphForSearchResult() {
    if (widget.searchQuery.isEmpty || widget.currentResultIndex < 0) return -1;

    int currentMatchCount = 0;
    final searchQuery = widget.searchQuery.toLowerCase();

    for (int i = 0; i < _paragraphs.length; i++) {
      final paragraphText = _paragraphs[i].toLowerCase();

      // Count matches in this paragraph
      int paragraphMatches = 0;
      int startIndex = 0;
      while (true) {
        int index = paragraphText.indexOf(searchQuery, startIndex);
        if (index == -1) break;
        paragraphMatches++;
        startIndex = index + 1;
      }

      if (widget.currentResultIndex < currentMatchCount + paragraphMatches) {
        return i;
      }

      currentMatchCount += paragraphMatches;
    }

    return -1;
  }

  // Calculate the local search index within a specific paragraph
  int _getLocalSearchIndex(int paragraphIndex) {
    if (widget.searchQuery.isEmpty || widget.currentResultIndex < 0) return -1;

    int currentMatchCount = 0;
    final searchQuery = widget.searchQuery.toLowerCase();

    for (int i = 0; i < paragraphIndex; i++) {
      final paragraphText = _paragraphs[i].toLowerCase();
      int startIndex = 0;
      while (true) {
        int index = paragraphText.indexOf(searchQuery, startIndex);
        if (index == -1) break;
        currentMatchCount++;
        startIndex = index + 1;
      }
    }

    final currentParagraphText = _paragraphs[paragraphIndex].toLowerCase();
    int paragraphMatches = 0;
    int startIndex = 0;
    while (true) {
      int index = currentParagraphText.indexOf(searchQuery, startIndex);
      if (index == -1) break;
      paragraphMatches++;
      startIndex = index + 1;
    }

    if (widget.currentResultIndex >= currentMatchCount &&
        widget.currentResultIndex < currentMatchCount + paragraphMatches) {
      return widget.currentResultIndex - currentMatchCount;
    }

    return -1;
  }

  void _scrollToSearchResult() {
    if (!_scrollController.hasClients || widget.searchQuery.isEmpty) return;

    final targetParagraphIndex = _findParagraphForSearchResult();

    if (targetParagraphIndex >= 0 && targetParagraphIndex < _paragraphKeys.length) {
      final targetKey = _paragraphKeys[targetParagraphIndex];
      final context = targetKey.currentContext;

      if (context != null) {
        Scrollable.ensureVisible(
          context,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
          alignment: 0.40,
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.content.isEmpty) {
      return const SizedBox.shrink();
    }

    return SelectionArea(
      child: SingleChildScrollView(
        controller: _scrollController,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.searchQuery.isNotEmpty)
              ..._paragraphs.asMap().entries.map((entry) {
                final index = entry.key;
                final paragraph = entry.value;
                final localSearchIndex = _getLocalSearchIndex(index);

                // Reset global counter at the start of rendering
                if (index == 0) {
                  _resetGlobalCounter();
                }

                return Container(
                  key: index < _paragraphKeys.length ? _paragraphKeys[index] : null,
                  margin: const EdgeInsets.only(bottom: 8),
                  child: _getMarkdownWidgetWithSearch(
                    context,
                    paragraph,
                    searchQuery: widget.searchQuery,
                    currentResultIndex: localSearchIndex,
                  ),
                );
              }).toList()
            else
              _getMarkdownWidgetWithSearch(context, widget.content),
          ],
        ),
      ),
    );
  }

  // Preprocess markdown to ensure proper spacing around headings and horizontal rules
  // This fixes issues where text directly before/after --- becomes a setext heading
  String _preprocessMarkdown(String content) {
    var processed = content;

    // Add blank line BEFORE horizontal rules if not present (prevents setext headings)
    // This is critical: text followed directly by --- becomes an H2 heading!
    processed = processed.replaceAllMapped(
      RegExp(r'([^\n])\n(---+)(\n|$)'),
      (match) => '${match.group(1)}\n\n${match.group(2)}${match.group(3)}',
    );

    // Add blank line after headings if not present (# through ######)
    processed = processed.replaceAllMapped(
      RegExp(r'(^|\n)(#{1,6}\s+[^\n]+)\n(?!\n)'),
      (match) => '${match.group(1)}${match.group(2)}\n\n',
    );

    // Add blank line after horizontal rules if not present
    processed = processed.replaceAllMapped(
      RegExp(r'(^|\n)(---+)\n(?!\n)'),
      (match) => '${match.group(1)}${match.group(2)}\n\n',
    );

    return processed;
  }

  // Custom markdown widget with search functionality
  Widget _getMarkdownWidgetWithSearch(BuildContext context, String content,
      {String searchQuery = '', int currentResultIndex = -1}) {
    // Check for generative UI tags
    final hasGenerativeTags = XmlTagParser.containsGenerativeTags(content);

    // If content has generative tags and no search, use GenerativeMarkdownWidget
    if (hasGenerativeTags && searchQuery.isEmpty) {
      return GenerativeMarkdownWidget(content: content);
    }

    // If content has generative tags WITH search, we need to handle it specially
    if (hasGenerativeTags && searchQuery.isNotEmpty) {
      return _buildGenerativeContentWithSearch(context, content, searchQuery, currentResultIndex);
    }

    // Preprocess markdown to fix spacing issues
    String processedContent = _preprocessMarkdown(content);

    // If there's a search query, inject highlight tags
    if (searchQuery.isNotEmpty) {
      processedContent = _highlightSearchInMarkdown(processedContent, searchQuery, currentResultIndex);
    }

    return MarkdownBody(
      selectable: false,
      shrinkWrap: true,
      builders: searchQuery.isNotEmpty
          ? {
              'highlight': _SearchHighlightBuilder(),
            }
          : {},
      inlineSyntaxes: searchQuery.isNotEmpty
          ? [
              _SearchHighlightSyntax(),
            ]
          : [],
      styleSheet: MarkdownStyleHelper.getStyleSheet(context),
      data: processedContent,
    );
  }

  // Build generative UI content with search highlighting for markdown segments only
  Widget _buildGenerativeContentWithSearch(
    BuildContext context,
    String content,
    String searchQuery,
    int currentResultIndex,
  ) {
    final parser = XmlTagParser();
    final segments = parser.parse(content);

    int currentMatchOffset = 0;

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
        children: segments.map((segment) {
          if (segment is MarkdownSegment) {
            // Preprocess markdown to fix spacing issues
            final preprocessed = _preprocessMarkdown(segment.content);

            // Count matches in this segment to track offset
            final matchCount = _countMatches(preprocessed, searchQuery);
            final localIndex = currentResultIndex >= currentMatchOffset &&
                    currentResultIndex < currentMatchOffset + matchCount
                ? currentResultIndex - currentMatchOffset
                : -1;

            currentMatchOffset += matchCount;

            // Apply search highlighting to markdown content
            final processedContent =
                _highlightSearchInMarkdown(preprocessed, searchQuery, localIndex);

            return MarkdownBody(
              selectable: false,
              shrinkWrap: true,
              builders: {'highlight': _SearchHighlightBuilder()},
              inlineSyntaxes: [_SearchHighlightSyntax()],
              styleSheet: MarkdownStyleHelper.getStyleSheet(context),
              data: processedContent,
            );
          } else if (segment is RichListSegment) {
            return RichListWidget(
              items: segment.items,
              onUrlTap: (url) => InAppBrowser.open(context, url),
            );
          } else if (segment is PieChartSegment) {
            return GenerativeBarChartWidget(data: segment.data);
          }
          return const SizedBox.shrink();
        }).toList(),
      ),
    );
  }

  int _countMatches(String content, String searchQuery) {
    if (searchQuery.isEmpty) return 0;
    final pattern = RegExp(RegExp.escape(searchQuery), caseSensitive: false);
    return pattern.allMatches(content).length;
  }

  static void _resetGlobalCounter() {
    // Reset counter logic if needed
  }

  String _highlightSearchInMarkdown(
    String content,
    String searchQuery,
    int currentResultIndex,
  ) {
    if (searchQuery.isEmpty) return content;

    final pattern = RegExp.escape(searchQuery);
    final matches = RegExp(pattern, caseSensitive: false).allMatches(content);
    if (matches.isEmpty) return content;

    String result = content;
    int offset = 0;
    int matchIndex = 0;

    for (final match in matches) {
      final isCurrentMatch = matchIndex == currentResultIndex;

      final openTag = isCurrentMatch ? '{{H current}}' : '{{H}}';
      const closeTag = '{{/H}}';

      final start = match.start + offset;
      final end = match.end + offset;

      result = result.substring(0, start) + openTag + result.substring(start, end) + closeTag + result.substring(end);

      offset += openTag.length + closeTag.length;
      matchIndex++;
    }

    return result;
  }
}

class _SearchHighlightSyntax extends md.InlineSyntax {
  _SearchHighlightSyntax() : super(r'(\{\{H(?: current)?\}\})(.*?)(\{\{/H\}\})');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final isCurrent = match.group(1)!.contains('current');
    final content = match.group(2) ?? '';

    final element = md.Element('highlight', [md.Text(content)]);
    if (isCurrent) {
      element.attributes['current'] = 'true';
    }
    parser.addNode(element);
    return true;
  }
}

// Custom builder for search highlighting
class _SearchHighlightBuilder extends MarkdownElementBuilder {
  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    if (element.tag != 'highlight') return null;

    final isCurrent = element.attributes['current'] == 'true';

    return RichText(
      text: TextSpan(
        text: element.textContent,
        style: (preferredStyle ?? const TextStyle()).copyWith(
          backgroundColor: isCurrent ? Colors.orange : Colors.deepPurple,
          color: Colors.white,
        ),
      ),
    );
  }
}
