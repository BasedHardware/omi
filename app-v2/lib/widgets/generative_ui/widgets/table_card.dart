import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/table_data.dart';

/// Card showing a styled table with optional title.
class TableCard extends StatelessWidget {
  final TableDisplayData data;

  const TableCard({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
              borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
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
      border: TableBorder(verticalInside: BorderSide(color: Colors.white.withValues(alpha: 0.1))),
      children: [
        if (data.headerRow != null) _buildHeaderRow(data.headerRow!),
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
        color: AppColors.backgroundTertiary,
        border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.15))),
      ),
      children: List.generate(data.columnCount, (index) {
        final cell = index < row.cells.length ? row.cells[index] : null;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingM, vertical: 10),
          child: Text(
            cell?.content ?? '',
            style: const TextStyle(color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w600),
          ),
        );
      }),
    );
  }

  TableRow _buildDataRow(TableRowData row, int index, bool isLast) {
    return TableRow(
      decoration: BoxDecoration(
        color: index.isEven ? Colors.white.withValues(alpha: 0.02) : Colors.transparent,
        border: !isLast ? Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.08))) : null,
      ),
      children: List.generate(data.columnCount, (colIndex) {
        final cell = colIndex < row.cells.length ? row.cells[colIndex] : null;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingM, vertical: 10),
          child: Text(
            cell?.content ?? '',
            style: const TextStyle(color: AppColors.textSecondary, fontSize: 13, height: 1.4),
          ),
        );
      }),
    );
  }
}
