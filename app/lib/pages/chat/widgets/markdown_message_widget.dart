import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/utils/platform/platform_service.dart';

Widget getMarkdownWidget(BuildContext context, String message, {Function(String)? onAskOmi}) {
  return MarkdownBody(
      data: message.trimRight(),
      selectable: PlatformService.isMacOS,
      styleSheet: MarkdownStyleSheet(
        p: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
        a: const TextStyle(color: Colors.blue, decoration: TextDecoration.underline),
        listBullet: const TextStyle(color: Colors.white, fontSize: 16),
        blockquote: const TextStyle(
          color: Colors.white,
          fontSize: 16,
          height: 1.4,
          backgroundColor: Colors.transparent,
        ),
        blockquoteDecoration: BoxDecoration(
          color: const Color(0xFF35343B),
          borderRadius: BorderRadius.circular(4),
        ),
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
