import 'package:flutter/material.dart';
import '../models/table_data.dart';

/// Card showing a styled table with optional title
class TableCard extends StatelessWidget {
  final TableDisplayData data;

  const TableCard({
    super.key,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(
                color: Colors.white.withOpacity(0.1),
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: _buildTable(),
          ),
        ),
      ),
    );
  }

  Widget _buildTable() {
    return Table(
      defaultColumnWidth: const IntrinsicColumnWidth(),
      border: TableBorder(
        verticalInside: BorderSide(
          color: Colors.white.withOpacity(0.1),
        ),
      ),
      children: [
        // Header row
        if (data.headerRow != null) _buildHeaderRow(data.headerRow!),
        // Data rows
        ...data.dataRows.asMap().entries.map((entry) {
          final index = entry.key;
          final row = entry.value;
          final isLast = index == data.dataRows.length - 1;
          return _buildDataRow(row, index, isLast);
        }),
      ],
    );
  }

  TableRow _buildHeaderRow(TableRowData row) {
    return TableRow(
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.1),
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.15),
          ),
        ),
      ),
      children: List.generate(data.columnCount, (index) {
        final cell = index < row.cells.length ? row.cells[index] : null;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Text(
            cell?.content ?? '',
            style: TextStyle(
              color: Colors.white.withOpacity(0.9),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        );
      }),
    );
  }

  TableRow _buildDataRow(TableRowData row, int index, bool isLast) {
    return TableRow(
      decoration: BoxDecoration(
        color: index.isEven ? Colors.white.withOpacity(0.02) : Colors.transparent,
        border: !isLast
            ? Border(
                bottom: BorderSide(
                  color: Colors.white.withOpacity(0.08),
                ),
              )
            : null,
      ),
      children: List.generate(data.columnCount, (colIndex) {
        final cell = colIndex < row.cells.length ? row.cells[colIndex] : null;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Text(
            cell?.content ?? '',
            style: TextStyle(
              color: Colors.white.withOpacity(0.75),
              fontSize: 13,
              height: 1.4,
            ),
          ),
        );
      }),
    );
  }
}
