import '../models/followups_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <followups> tags containing journalist follow-up tasks.
///
/// Example:
/// ```xml
/// <followups>
///   <item type="Fact-check">Confirm exact budget cut number and % vs last year</item>
///   <item type="Verification">Call transit authority about route 17 cancelation</item>
///   <item type="Question">Check if hearing date is officially on city calendar</item>
/// </followups>
/// ```
class FollowupsParser extends BaseTagParser {
  // Pattern to match <followups>...</followups> blocks
  static final _followupsPattern = RegExp(
    r'<followups>([\s\S]*?)</followups>',
    caseSensitive: false,
  );

  // Pattern to match <item ...>...</item> tags within followups
  static final _itemPattern = RegExp(
    r'<item\s+([^>]*)>([\s\S]*?)</item>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _followupsPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final innerContent = match.group(1) ?? '';
    return _parseFollowups(innerContent);
  }

  FollowupsSegment? _parseFollowups(String innerContent) {
    final items = <FollowupItemData>[];

    for (final itemMatch in _itemPattern.allMatches(innerContent)) {
      final itemAttrString = itemMatch.group(1) ?? '';
      final itemContent = itemMatch.group(2) ?? '';
      final itemAttrs = parseAttributes(itemAttrString);

      items.add(FollowupItemData.fromParsed(
        attributes: itemAttrs,
        innerContent: itemContent,
      ));
    }

    if (items.isEmpty) return null;

    return FollowupsSegment(FollowupsDisplayData(
      items: items,
    ));
  }
}
