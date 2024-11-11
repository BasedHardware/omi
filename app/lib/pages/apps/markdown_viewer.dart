import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:url_launcher/url_launcher.dart';

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
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(widget.title),
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView(
        children: [
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.only(left: 16.0, right: 24),
            child: MarkdownBody(
              shrinkWrap: true,
              styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
                a: const TextStyle(fontSize: 18, height: 1.2),
                p: const TextStyle(fontSize: 16, height: 1.2),
                blockquote: const TextStyle(
                  fontSize: 16,
                  height: 1.2,
                  backgroundColor: Colors.transparent,
                  color: Colors.black,
                ),
                blockquoteDecoration: BoxDecoration(
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(4),
                ),
                code: const TextStyle(
                  fontSize: 16,
                  height: 1.2,
                  backgroundColor: Colors.transparent,
                  decoration: TextDecoration.none,
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
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
          )
        ],
      ),
    );
  }
}
