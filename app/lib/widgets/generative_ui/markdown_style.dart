import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

/// Shared markdown stylesheet to ensure consistent styling across all markdown renderers
class MarkdownStyleHelper {
  static MarkdownStyleSheet getStyleSheet(BuildContext context) {
    var style = const TextStyle(
      inherit: false, // Don't inherit from parent - use explicit values only
      color: Colors.white,
      fontSize: 16,
      height: 1.5,
      fontStyle: FontStyle.normal,
      fontWeight: FontWeight.normal,
      letterSpacing: 0,
      wordSpacing: 0,
      textBaseline: TextBaseline.alphabetic,
      decoration: TextDecoration.none,
    );

    return MarkdownStyleSheet(
      // Paragraph
      p: style,
      pPadding: const EdgeInsets.only(bottom: 12),

      // Links
      a: style.copyWith(decoration: TextDecoration.underline),

      // Emphasis (italic) - IMPORTANT: Keep same font style as regular text
      em: style.copyWith(fontStyle: FontStyle.italic),

      // Strong (bold)
      strong: style.copyWith(fontWeight: FontWeight.bold),

      // Delete/strikethrough
      del: style.copyWith(decoration: TextDecoration.lineThrough),

      // Blockquote - styled with left border accent
      blockquote: style.copyWith(
        color: Colors.white.withOpacity(0.85),
        fontStyle: FontStyle.italic,
      ),
      blockquoteDecoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        border: const Border(
          left: BorderSide(
            color: Color(0xFF8B5CF6),
            width: 3,
          ),
        ),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(4),
          bottomRight: Radius.circular(4),
        ),
      ),
      blockquotePadding: const EdgeInsets.fromLTRB(14, 12, 14, 12),

      // Code
      code: style.copyWith(
        backgroundColor: const Color(0xFF35343B),
        fontFamily: 'monospace',
        fontSize: 14,
      ),
      codeblockDecoration: BoxDecoration(
        color: const Color(0xFF35343B),
        borderRadius: BorderRadius.circular(4),
      ),
      codeblockPadding: const EdgeInsets.all(12),

      // Headings
      h1: style.copyWith(fontSize: 24, fontWeight: FontWeight.bold),
      h2: style.copyWith(fontSize: 22, fontWeight: FontWeight.bold),
      h3: style.copyWith(fontSize: 20, fontWeight: FontWeight.bold),
      h4: style.copyWith(fontSize: 18, fontWeight: FontWeight.bold),
      h5: style.copyWith(fontSize: 16, fontWeight: FontWeight.bold),
      h6: style.copyWith(fontSize: 14, fontWeight: FontWeight.bold),
      h1Padding: const EdgeInsets.only(bottom: 12),
      h2Padding: const EdgeInsets.only(bottom: 10),
      h3Padding: const EdgeInsets.only(bottom: 8),
      h4Padding: const EdgeInsets.only(bottom: 6),
      h5Padding: const EdgeInsets.only(bottom: 4),
      h6Padding: const EdgeInsets.only(bottom: 4),

      // Lists
      listBullet: style,
      listBulletPadding: const EdgeInsets.only(right: 4),
      listIndent: 8.0,

      // Text scaling
      textScaler: TextScaler.noScaling,

      // Tables
      tableHead: style.copyWith(fontWeight: FontWeight.bold),
      tableBody: style,
      tableBorder: TableBorder.all(color: Colors.white24),
      tableColumnWidth: const FlexColumnWidth(),
      tableCellsPadding: const EdgeInsets.all(8),

      // Horizontal rule - subtle, barely visible
      horizontalRuleDecoration: BoxDecoration(
        border: Border(
          top: BorderSide(color: Colors.white.withOpacity(0.08), width: 0.5),
        ),
      ),

      // Spacing
      blockSpacing: 8.0,

      // Checkbox
      checkbox: style,
    );
  }
}
