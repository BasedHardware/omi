import 'package:flutter/material.dart';
import 'package:friend_private/utils/library/flutter_markdown/flutter_markdown.dart';

class ExpandableTextWidget extends StatefulWidget {
  final String text;
  final TextStyle style;
  final int maxCharacter;
  final String expandText;
  final String collapseText;
  final Color linkColor;
  final bool isExpanded;
  final Function toggleExpand;
  final Function onTap;

  const ExpandableTextWidget({
    super.key,
    required this.text,
    required this.style,
    required this.isExpanded,
    required this.toggleExpand,
    required this.onTap,
    this.maxCharacter = 300,
    this.expandText = 'Show More ↓',
    this.collapseText = 'Show Less ↑',
    this.linkColor = Colors.deepPurple,
  });

  @override
  _ExpandableTextWidgetState createState() => _ExpandableTextWidgetState();
}

class _ExpandableTextWidgetState extends State<ExpandableTextWidget> {
  @override
  Widget build(BuildContext context) {
    String displayedText = widget.isExpanded
        ? widget.text
        : (widget.text.length <= widget.maxCharacter)
            ? widget.text
            : '${widget.text.substring(0, widget.maxCharacter)}...';

    return SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () {
              widget.onTap();
            },
            child: Container(
              color: Colors.transparent,
              child: MarkdownBody(
                shrinkWrap: true,
                data: displayedText,
              ),
            ),
          ),
          if (widget.text.length > widget.maxCharacter)
            InkWell(
              onTap: () => widget.toggleExpand(),
              child: Padding(
                padding: const EdgeInsets.only(top: 4.0, right: 10, bottom: 4),
                child: Text(
                  widget.isExpanded ? widget.collapseText : widget.expandText,
                  style: const TextStyle(
                    color: Colors.deepPurple,
                    fontWeight: FontWeight.w500,
                    fontSize: 13,
                  ),
                ),
              ),
            )
          else
            Container(height: 5),
        ],
      ),
    );
  }
}
