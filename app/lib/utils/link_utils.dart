import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class LinkUtils {
  static final urlPattern = RegExp(
    r'(?:(?:https?|ftp):\/\/|www\.)[^\s/$.?#].[^\s]*',
    caseSensitive: false,
  );

  static bool containsMarkdown(String text) {
    return text.contains('**') || text.contains('##') || text.contains('*') || text.contains('`');
  }

  static List<TextSpan> buildTextSpans(
    String text, {
    TextStyle? defaultStyle,
    TextStyle? linkStyle,
  }) {
    final spans = <TextSpan>[];
    final defaultTextStyle = defaultStyle ?? const TextStyle();
    final urlTextStyle = linkStyle ??
        defaultStyle?.copyWith(
          color: Colors.blue,
          decoration: TextDecoration.underline,
          decorationColor: Colors.blue,
        ) ??
        const TextStyle(
          color: Colors.blue,
          decoration: TextDecoration.underline,
          decorationColor: Colors.blue,
        );

    text.splitMapJoin(
      urlPattern,
      onMatch: (match) {
        final url = match.group(0)!;
        final displayUrl = url.replaceFirst(RegExp(r'^https?://'), '');

        spans.add(TextSpan(
          text: displayUrl,
          style: urlTextStyle,
          recognizer: TapGestureRecognizer()..onTap = () => launchUrlString(url),
        ));
        return '';
      },
      onNonMatch: (text) {
        if (text.isNotEmpty) {
          spans.add(TextSpan(text: text, style: defaultTextStyle));
        }
        return '';
      },
    );

    return spans;
  }

  static Future<void> launchUrlString(String url) async {
    try {
      final uri = url.startsWith(RegExp(r'https?://')) ? Uri.parse(url) : Uri.parse('https://$url');

      if (await canLaunchUrl(uri)) {
        await launchUrl(
          uri,
          mode: LaunchMode.externalApplication,
          webViewConfiguration: const WebViewConfiguration(
            enableJavaScript: true,
          ),
        );
      } else {
        debugPrint('Could not launch URL: $url');
      }
    } catch (e, stackTrace) {
      debugPrint('Error launching URL: $e\n$stackTrace');
    }
  }

  static Widget buildRichText(
    String text, {
    TextStyle? style,
    TextAlign? textAlign,
    int? maxLines,
    TextOverflow? overflow,
  }) {
    return RichText(
      text: TextSpan(
        children: buildTextSpans(
          text,
          defaultStyle: style,
        ),
        style: style,
      ),
      textAlign: textAlign ?? TextAlign.start,
      maxLines: maxLines,
      overflow: overflow ?? TextOverflow.clip,
    );
  }
}
