import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/ui/ui.dart';

/// Opens a link tapped in a chat reply. The Flutter Markdown body and the native rich reply both
/// hand their links here, so neither renderer opens a URL on its own.
Future<void> openChatMarkdownLink(String href) async {
  await launchUrl(Uri.parse(href));
}

Widget getMarkdownWidget(BuildContext context, String message, {Function(String)? onAskOmi}) {
  return MarkdownBody(
    data: message.trimRight(),
    selectable: false,
    styleSheet: MarkdownStyleSheet(
      p: OmiType.callout.copyWith(height: 1.4),
      // Links are neutral (INV-UI-1): white and underlined, not a blue accent.
      a: TextStyle(color: OmiColors.textPrimary, decoration: TextDecoration.underline),
      listBullet: OmiType.callout,
      blockquote: OmiType.callout.copyWith(height: 1.4, backgroundColor: Colors.transparent),
      blockquoteDecoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
      code: TextStyle(
        color: OmiColors.textPrimary,
        backgroundColor: Colors.transparent,
        fontFamily: 'monospace',
      ),
      codeblockDecoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
    ),
    onTapLink: (text, href, title) {
      if (href != null) {
        openChatMarkdownLink(href);
      }
    },
  );
}
