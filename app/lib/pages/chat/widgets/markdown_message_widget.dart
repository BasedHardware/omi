import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

Widget getMarkdownWidget(BuildContext context, String content) {
  var style = TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3);
  return MarkdownBody(
    shrinkWrap: true,
    styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      a: style,
      p: style,
      blockquote: style.copyWith(
        backgroundColor: Colors.transparent,
        color: Colors.black,
      ),
      blockquoteDecoration: BoxDecoration(
        color: Colors.grey.shade800,
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
