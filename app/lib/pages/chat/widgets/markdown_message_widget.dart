import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

Widget getMarkdownWidget(BuildContext context, String message, {Function(String)? onAskOmi}) {
  return MarkdownBody(
      data: message.trimRight(),
      selectable: false,
      styleSheet: MarkdownStyleSheet(
        p: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
        a: const TextStyle(color: Colors.blue, decoration: TextDecoration.underline),
        listBullet: const TextStyle(color: Colors.white, fontSize: 16),
        code: const TextStyle(
          color: Colors.white,
          backgroundColor: Colors.transparent,
          fontFamily: 'monospace',
        ),
        codeblockDecoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(8),
        ),
      ),
      onTapLink: (text, href, title) {
        if (href != null) {
          launchUrl(Uri.parse(href));
        }
      },
    );
}
