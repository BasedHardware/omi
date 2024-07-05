import 'package:flutter/material.dart';

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final TextStyle style;
  final int maxLines;
  final String expandText;
  final String collapseText;
  final Color linkColor;
  final bool isExpanded;
  final Function toggleExpand;

  const ExpandableTextWidget({
    super.key,
    required this.text,
    required this.style,
    required this.isExpanded,
    required this.toggleExpand,
    this.maxLines = 3,
    this.expandText = 'show more ↓',
    this.collapseText = 'show less ↑',
    this.linkColor = Colors.deepPurple,
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
          Text(
            widget.text,
            style: widget.style,
            maxLines: widget.isExpanded ? 10000 : widget.maxLines,
            overflow: TextOverflow.ellipsis,
          ),
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
