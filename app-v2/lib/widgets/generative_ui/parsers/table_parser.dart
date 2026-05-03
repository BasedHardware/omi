import '../models/table_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for `<table>` tags with rows and cells.
class TableParser extends BaseTagParser {
  static final _tablePattern = RegExp(r'<table[^>]*>([\s\S]*?)</table>', caseSensitive: false);

  static final _attrPattern = RegExp(r'<table\s+([^>]*)>', caseSensitive: false);

  static final _rowPattern = RegExp(r'<row>([\s\S]*?)</row>', caseSensitive: false);

  static final _cellPattern = RegExp(r'<cell>([\s\S]*?)</cell>', caseSensitive: false);

  @override
  RegExp get pattern => _tablePattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final fullMatch = match.group(0) ?? '';
    final tableContent = match.group(1) ?? '';

    String tableAttrString = '';
    final attrMatch = _attrPattern.firstMatch(fullMatch);
    if (attrMatch != null) {
      tableAttrString = attrMatch.group(1) ?? '';
    }

    final table = _parseTable(tableAttrString, tableContent);
    if (table == null) return null;
    return TableSegment(table);
  }

  TableDisplayData? _parseTable(String tableAttrString, String tableContent) {
    final attributes = parseAttributes(tableAttrString);
    final title = attributes['title'];

    final rows = <TableRowData>[];

    for (final rowMatch in _rowPattern.allMatches(tableContent)) {
      final rowContent = rowMatch.group(1) ?? '';
      final cells = <TableCellData>[];

      for (final cellMatch in _cellPattern.allMatches(rowContent)) {
        final cellContent = cellMatch.group(1) ?? '';
        if (cellContent.trim().isNotEmpty) {
          cells.add(TableCellData.fromContent(cellContent));
        }
      }

      if (cells.isNotEmpty) {
        rows.add(TableRowData(cells: cells));
      }
    }

    if (rows.isEmpty) return null;

    return TableDisplayData(title: title, rows: rows);
  }
}
