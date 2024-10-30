import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final bool isExpanded;
  final Function toggleExpand;
  final TextStyle style;
  final int maxLines;
  final String expandText;
  final String collapseText;
  final Color linkColor;

  const ExpandableTextWidget({
    super.key,
    required this.text,
    required this.style,
    this.maxLines = 3,
    this.expandText = 'show more ↓',
    this.collapseText = 'show less ↑',
    this.linkColor = Colors.deepPurple,
    required this.isExpanded,
    required this.toggleExpand,
  });

  @override
  _ExpandableTextWidgetState createState() => _ExpandableTextWidgetState();
}

class _ExpandableTextWidgetState extends State<ExpandableTextWidget> {
  @override
  Widget build(BuildContext context) {
    final span = TextSpan(text: widget.text, style: widget.style);
    final tp = TextPainter(
      text: span,
      maxLines: widget.maxLines,
      textDirection: TextDirection.ltr,
    );
    tp.layout(maxWidth: MediaQuery.of(context).size.width);
    final isOverflowing = tp.didExceedMaxLines;

    return SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          MarkdownBody(
            shrinkWrap: true,
            styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
              a: widget.style,
              p: widget.style,
              blockquote: widget.style.copyWith(
                backgroundColor: Colors.transparent,
                color: Colors.black,
              ),
              blockquoteDecoration: BoxDecoration(
                color: Colors.grey.shade800,
                borderRadius: BorderRadius.circular(4),
              ),
              code: widget.style.copyWith(
                backgroundColor: Colors.transparent,
                decoration: TextDecoration.none,
                color: Colors.white,
                fontWeight: FontWeight.w600,
              ),
            ),
            data: widget.isExpanded ? widget.text : widget.text.length > 300 ?widget.text.substring(0, 300): widget.text,
          ),
          // Text(
          //   widget.text,
          //   style: widget.style,
          //   maxLines: widget.isExpanded ? 10000 : widget.maxLines,
          //   overflow: TextOverflow.ellipsis,
          // ),
          if (isOverflowing)
            InkWell(
              onTap: () => widget.toggleExpand(),
              child: Padding(
                padding: const EdgeInsets.only(top: 4.0),
                child: Text(
                  widget.isExpanded ? widget.collapseText : widget.expandText,
                  style: TextStyle(
                    color: Colors.deepPurple,
                    fontWeight: FontWeight.w500,
                    fontSize: widget.style.fontSize,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
