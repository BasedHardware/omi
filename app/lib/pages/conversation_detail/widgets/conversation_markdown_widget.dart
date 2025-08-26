import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:omi/utils/other/temp.dart';

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
  bool _isAutoScrolling = false;

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
        _isAutoScrolling = true;

        Scrollable.ensureVisible(
          context,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
          alignment: 0.05,
        ).then((_) {
          _isAutoScrolling = false;
        });
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

  // Custom markdown widget with search functionality
  Widget _getMarkdownWidgetWithSearch(BuildContext context, String content,
      {String searchQuery = '', int currentResultIndex = -1}) {
    var style = TextStyle(color: Colors.white, fontSize: 16, height: 1.5);

    String processedContent = content;

    // If there's a search query, inject highlight tags
    if (searchQuery.isNotEmpty) {
      processedContent = _highlightSearchInMarkdown(content, searchQuery, currentResultIndex);
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
      styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
        a: style,
        p: style.copyWith(
          height: 1.5,
        ),
        pPadding: const EdgeInsets.only(bottom: 12),
        blockquote: style.copyWith(
          backgroundColor: Colors.transparent,
          color: Colors.white,
        ),
        blockquoteDecoration: BoxDecoration(
          color: Color(0xFF35343B),
          borderRadius: BorderRadius.circular(4),
        ),
        code: style.copyWith(
          backgroundColor: Colors.transparent,
          decoration: TextDecoration.none,
          color: Colors.white,
          fontWeight: FontWeight.w500,
        ),
        strong: style.copyWith(
          fontWeight: FontWeight.bold,
        ),
      ),
      data: processedContent,
    );
  }

  static int _globalMatchCount = 0;

  static void _resetGlobalCounter() {
    _globalMatchCount = 0;
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

  String _stripMarkdownFormatting(String content) {
    // Remove bold (**text** or __text__)
    content = content.replaceAllMapped(
      RegExp(r'\*\*(.*?)\*\*|__(.*?)__'),
      (match) => match.group(1) ?? match.group(2) ?? '',
    );

    // Remove italic (*text* or _text_)
    content = content.replaceAllMapped(
      RegExp(r'\*(.*?)\*|_(.*?)_'),
      (match) => match.group(1) ?? match.group(2) ?? '',
    );

    // Remove headers (# ## ### etc.)
    content = content.replaceAll(
      RegExp(r'^#{1,6}\s+', multiLine: true),
      '',
    );

    content = content.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\([^\)]+\)'),
      (match) => match.group(1) ?? '',
    );

    content = content.replaceAll(
      RegExp(r'^[\s]*[-\*\+]\s+', multiLine: true),
      '',
    );

    return content;
  }

  TextSpan _buildHighlightedTextSpan(String content, String searchQuery, int currentResultIndex, TextStyle baseStyle) {
    if (searchQuery.isEmpty) {
      return TextSpan(text: content, style: baseStyle);
    }

    String displayContent = _stripMarkdownFormatting(content);

    final matches = RegExp(searchQuery, caseSensitive: false).allMatches(displayContent);
    if (matches.isEmpty) {
      return TextSpan(text: displayContent, style: baseStyle);
    }

    List<TextSpan> spans = [];
    int lastEnd = 0;
    int matchIndex = 0;

    for (final match in matches) {
      if (match.start > lastEnd) {
        spans.add(TextSpan(
          text: displayContent.substring(lastEnd, match.start),
          style: baseStyle,
        ));
      }

      final isCurrentMatch = matchIndex == currentResultIndex;
      spans.add(TextSpan(
        text: displayContent.substring(match.start, match.end),
        style: baseStyle.copyWith(
          backgroundColor: isCurrentMatch ? Colors.orange : Colors.deepPurple,
          color: Colors.white,
        ),
      ));

      lastEnd = match.end;
      matchIndex++;
    }

    if (lastEnd < displayContent.length) {
      spans.add(TextSpan(
        text: displayContent.substring(lastEnd),
        style: baseStyle,
      ));
    }

    return TextSpan(children: spans);
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
