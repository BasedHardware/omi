import 'package:flutter/material.dart';

import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/ui/ui.dart';

/// Omi's answer in chat (Omi v8 `.an`): the words in body type with room between the lines, and no
/// bubble. Headings take the weight and are never smaller than the words, and a "[1]" pointing at a
/// source is set small in the quiet ink.
Widget getMarkdownWidget(BuildContext context, String message, {Function(String)? onAskOmi}) {
  final words = OmiType.body.copyWith(height: 1.45);
  final heading = OmiType.headline.copyWith(height: 1.35);
  return MarkdownBody(
    data: message.trimRight(),
    selectable: false,
    inlineSyntaxes: [_SourceMarkerSyntax()],
    builders: {
      _SourceMarkerSyntax.tag: _SourceMarkerBuilder(OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
    },
    styleSheet: MarkdownStyleSheet(
      p: words,
      h1: OmiType.title3.copyWith(height: 1.3),
      h2: heading,
      h3: heading,
      h4: heading,
      h5: heading,
      h6: heading,
      // Links are neutral (INV-UI-1): white and underlined, not a blue accent.
      a: TextStyle(color: OmiColors.textPrimary, decoration: TextDecoration.underline),
      listBullet: words,
      blockquote: words.copyWith(backgroundColor: Colors.transparent),
      blockquoteDecoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
      code: TextStyle(
        color: OmiColors.textPrimary,
        backgroundColor: Colors.transparent,
        fontFamily: 'monospace',
      ),
      codeblockDecoration: BoxDecoration(color: OmiCanvas.cardOf(context), borderRadius: OmiRadius.smAll),
    ),
    onTapLink: (text, href, title) {
      if (href != null) {
        launchUrl(Uri.parse(href));
      }
    },
  );
}

/// "[1]" in an answer: its pointer to a source. Not a link, so "[1](url)" stays one.
class _SourceMarkerSyntax extends md.InlineSyntax {
  _SourceMarkerSyntax() : super(r'\[\d{1,2}\](?!\()');

  static const String tag = 'sourceMarker';

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    parser.addNode(md.Element.text(tag, match[0]!));
    return true;
  }
}

/// Draws a source marker in [style], inside the sentence it ends.
class _SourceMarkerBuilder extends MarkdownElementBuilder {
  _SourceMarkerBuilder(this.style);

  final TextStyle style;

  @override
  Widget? visitElementAfterWithContext(
    BuildContext context,
    md.Element element,
    TextStyle? preferredStyle,
    TextStyle? parentStyle,
  ) =>
      Text.rich(TextSpan(text: element.textContent, style: style));
}
