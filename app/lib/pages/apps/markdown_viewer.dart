import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';

class MarkdownViewer extends StatefulWidget {
  final String markdown;
  final String title;
  const MarkdownViewer({super.key, required this.markdown, required this.title});

  @override
  State<MarkdownViewer> createState() => _MarkdownViewerState();
}

class _MarkdownViewerState extends State<MarkdownViewer> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(backgroundColor: OmiColors.surface0, leading: const OmiBackButton(), title: Text(widget.title)),
      backgroundColor: OmiColors.surface0,
      body: ListView(
        children: [
          const SizedBox(height: OmiSpacing.md),
          Padding(
            padding: const EdgeInsets.only(left: OmiSpacing.md, right: OmiSpacing.xl),
            child: MarkdownBody(
              shrinkWrap: true,
              styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
                a: OmiType.body.copyWith(height: 1.2),
                p: OmiType.callout.copyWith(height: 1.2),
                // Quotes read as secondary text on a raised surface (the old black text on a dark
                // grey fill was nearly invisible).
                blockquote: OmiType.callout.copyWith(
                  height: 1.2,
                  backgroundColor: Colors.transparent,
                  color: OmiColors.textSecondary,
                ),
                blockquoteDecoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                code: OmiType.callout.copyWith(
                  height: 1.2,
                  backgroundColor: Colors.transparent,
                  decoration: TextDecoration.none,
                  fontWeight: FontWeight.w500,
                ),
              ),
              data: widget.markdown,
              imageBuilder: (uri, title, alt) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8.0),
                  child: Image.network(uri.toString()),
                );
                // return Container();
              },
              onTapLink: (text, href, title) {
                if (href != null) {
                  if (href.contains('?')) {
                    href += '&uid=${SharedPreferencesUtil().uid}';
                  } else {
                    href += '?uid=${SharedPreferencesUtil().uid}';
                  }
                  launchUrl(Uri.parse(href));
                }
              },
            ),
          ),
        ],
      ),
    );
  }
}
