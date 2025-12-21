/// Data model for a table cell
class TableCellData {
  final String content;

  const TableCellData({required this.content});

  factory TableCellData.fromContent(String content) {
    return TableCellData(content: content.trim());
  }
}

/// Data model for a table row
class TableRowData {
  final List<TableCellData> cells;

  const TableRowData({required this.cells});

  bool get isEmpty => cells.isEmpty;
  int get cellCount => cells.length;
}

/// Data model for a complete table
class TableDisplayData {
  final String? title;
  final List<TableRowData> rows;

  const TableDisplayData({
    this.title,
    this.rows = const [],
  });

  bool get isEmpty => rows.isEmpty;
  bool get hasTitle => title != null && title!.isNotEmpty;
  bool get hasHeader => rows.isNotEmpty;

  /// First row is treated as header
  TableRowData? get headerRow => rows.isNotEmpty ? rows.first : null;

  /// Data rows (all rows except the first/header)
  List<TableRowData> get dataRows => rows.length > 1 ? rows.sublist(1) : [];

  /// Maximum number of columns across all rows
  int get columnCount {
    if (rows.isEmpty) return 0;
    return rows.map((r) => r.cellCount).reduce((a, b) => a > b ? a : b);
  }
}
