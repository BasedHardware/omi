import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

Widget getMarkdownWidget(BuildContext context, String content) {
  var style = TextStyle(color: Colors.white, fontSize: 16, height: 1.5);
  return MarkdownBody(
    selectable: false,
    shrinkWrap: true,
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
    ),
    data: content,
  );
}
