import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/native_rich_text.dart';
import 'package:omi/utils/l10n_extensions.dart';

class MarkdownViewer extends StatefulWidget {
  final String markdown;
  final String title;
  const MarkdownViewer({super.key, required this.markdown, required this.title});

  @override
  State<MarkdownViewer> createState() => _MarkdownViewerState();
}

class _MarkdownViewerState extends State<MarkdownViewer> {
  Future<void> _openLink(String href) async {
    href += '${href.contains('?') ? '&' : '?'}uid=${SharedPreferencesUtil().uid}';
    await launchUrl(Uri.parse(href));
  }

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
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
                blockquoteDecoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
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
                  _openLink(href);
                }
              },
            ),
          ),
        ],
      ),
    );
    if (!iosSwiftUiEnabled) return classic;
    final links = nativeRichTextLinks(widget.markdown);
    return Scaffold(
        body: IosNativeSurface(
            title: widget.title,
            fallback: classic,
            toolbar: [
              NativeRow('markdown_back', context.l10n.back,
                  symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop())
            ],
            sections: [
              NativeSection('markdown', [
                for (final (index, block) in nativeRichText(widget.markdown).indexed)
                  NativeRow('markdown_block:$index', nativeRichBlockText(block),
                      kind: 'rich_text',
                      blocks: [block],
                      options: links,
                      action: (value) => value is String && links.containsKey(value) ? _openLink(links[value]!) : null),
              ])
            ],
            reader: const NativeReader()));
  }
}
