import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/widgets/generative_ui/generative_ui.dart';

Widget getMarkdownWidget(BuildContext context, String content, {bool enableGenerativeUI = true}) {
  // Check if content contains generative UI tags
  if (enableGenerativeUI && XmlTagParser.containsGenerativeTags(content)) {
    return GenerativeMarkdownWidget(content: content);
  }

  // Original markdown rendering using shared style helper
  return MarkdownBody(
    selectable: false,
    shrinkWrap: true,
    onTapLink: (text, href, title) async {
      if (href != null) {
        final uri = Uri.parse(href);
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    },
    styleSheet: MarkdownStyleHelper.getStyleSheet(context),
    data: content,
  );
}
