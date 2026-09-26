/// Markdown flattened to one line of plain text, for previews that have no room for formatting
/// (conversation rows, search hits): no "## " headings, list bullets, quote marks, emphasis or code
/// markers, and links keep only their words.
abstract final class OmiPlainText {
  static final _heading = RegExp(r'^\s{0,3}#{1,6}\s+', multiLine: true);
  static final _quote = RegExp(r'^\s{0,3}>\s?', multiLine: true);
  static final _bullet = RegExp(r'^\s*(?:[-*+•]|\d+[.)])\s+', multiLine: true);
  static final _rule = RegExp(r'^\s{0,3}(?:[-*_]\s*){3,}$', multiLine: true);
  static final _image = RegExp(r'!\[([^\]]*)\]\([^)]*\)');
  static final _link = RegExp(r'\[([^\]]+)\]\([^)]*\)');
  static final _strong = RegExp(r'(\*\*|__)(.+?)\1');
  static final _emphasis = RegExp(r'(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])');
  static final _strike = RegExp(r'~~(.+?)~~');
  static final _code = RegExp(r'`{1,3}([^`]*)`{1,3}');
  static final _space = RegExp(r'\s+');

  static String fromMarkdown(String markdown) {
    return markdown
        .replaceAll(_rule, ' ')
        .replaceAll(_heading, '')
        .replaceAll(_quote, '')
        .replaceAll(_bullet, '')
        .replaceAllMapped(_image, (m) => m[1]!)
        .replaceAllMapped(_link, (m) => m[1]!)
        .replaceAllMapped(_strong, (m) => m[2]!)
        .replaceAllMapped(_strike, (m) => m[1]!)
        .replaceAllMapped(_emphasis, (m) => m[2]!)
        .replaceAllMapped(_code, (m) => m[1]!)
        .replaceAll(_space, ' ')
        .trim();
  }
}
