import 'package:flutter/material.dart';
import 'package:friend_private/services/translation_service.dart';

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final bool isExpanded;
  final Function toggleExpand;
  final TextStyle style;
  final int maxLines;
  final Color linkColor;

  const ExpandableTextWidget({
    super.key,
    required this.text,
    required this.style,
    this.maxLines = 3,
    this.linkColor = Colors.deepPurple,
    required this.isExpanded,
    required this.toggleExpand
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
                  widget.isExpanded ? '${TranslationService.translate('show less')} ↑' : '${TranslationService.translate('show more')} ↓',
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
