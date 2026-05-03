import '../models/quote_board_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for `<quote-board>` tags containing journalist quotes.
class QuoteBoardParser extends BaseTagParser {
  static final _quoteBoardPattern = RegExp(r'<quote-board>([\s\S]*?)</quote-board>', caseSensitive: false);

  static final _quotePattern = RegExp(r'<quote\s+([^>]*)>([\s\S]*?)</quote>', caseSensitive: false);

  @override
  RegExp get pattern => _quoteBoardPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final innerContent = match.group(1) ?? '';
    return _parseQuoteBoard(innerContent);
  }

  QuoteBoardSegment? _parseQuoteBoard(String innerContent) {
    final quotes = <QuoteData>[];

    for (final quoteMatch in _quotePattern.allMatches(innerContent)) {
      final quoteAttrString = quoteMatch.group(1) ?? '';
      final quoteContent = quoteMatch.group(2) ?? '';
      final quoteAttrs = parseAttributes(quoteAttrString);

      quotes.add(QuoteData.fromParsed(attributes: quoteAttrs, innerContent: quoteContent));
    }

    if (quotes.isEmpty) return null;

    return QuoteBoardSegment(QuoteBoardDisplayData(quotes: quotes));
  }
}
