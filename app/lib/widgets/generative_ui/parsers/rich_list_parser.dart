import '../models/rich_list_item_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <rich-list> tags containing item elements.
///
/// Example:
/// ```xml
/// <rich-list>
///   <item title="Title" description="Description" thumb="https://..." url="https://..."/>
/// </rich-list>
/// ```
class RichListParser extends BaseTagParser {
  // Pattern to match <rich-list>...</rich-list> blocks
  static final _richListPattern = RegExp(
    r'<rich-list\s*>([\s\S]*?)</rich-list>',
    caseSensitive: false,
  );

  // Pattern to match <item .../> tags within rich-list
  // Properly handles quoted attributes containing special characters like URLs
  static final _itemPattern = RegExp(
    r'<item\s+((?:[^>"]*|"[^"]*")+)\s*\/?>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _richListPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final innerContent = match.group(1) ?? '';
    return _parseRichList(innerContent);
  }

  RichListSegment? _parseRichList(String innerContent) {
    final items = <RichListItemData>[];
    final matches = _itemPattern.allMatches(innerContent);

    for (final itemMatch in matches) {
      final attributeString = itemMatch.group(1) ?? '';
      final attributes = parseAttributes(attributeString);
      items.add(RichListItemData.fromAttributes(attributes));
    }

    if (items.isEmpty) return null;
    return RichListSegment(items);
  }
}
