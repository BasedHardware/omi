import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/ui/ui.dart';

Widget getMarkdownWidget(BuildContext context, String message, {Function(String)? onAskOmi}) {
  return MarkdownBody(
    data: message.trimRight(),
    selectable: false,
    styleSheet: MarkdownStyleSheet(
      p: OmiType.callout.copyWith(height: 1.4),
      // Links are neutral (INV-UI-1): white and underlined, not a blue accent.
      a: const TextStyle(color: OmiColors.textPrimary, decoration: TextDecoration.underline),
      listBullet: OmiType.callout,
      blockquote: OmiType.callout.copyWith(height: 1.4, backgroundColor: Colors.transparent),
      blockquoteDecoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
      code: const TextStyle(
        color: OmiColors.textPrimary,
        backgroundColor: Colors.transparent,
        fontFamily: 'monospace',
      ),
      codeblockDecoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
    ),
    onTapLink: (text, href, title) {
      if (href != null) {
        launchUrl(Uri.parse(href));
      }
    },
  );
}
