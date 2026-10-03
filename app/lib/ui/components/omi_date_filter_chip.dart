import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OmiDateFilterChip extends StatelessWidget {
  const OmiDateFilterChip({super.key, required this.start, this.end, required this.onClear});

  final DateTime start;
  final DateTime? end;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final dates = OmiDateFormat.of(context);
    final end = this.end;
    final sameDay = end == null || (end.year == start.year && end.month == start.month && end.day == start.day);
    final formatted = sameDay ? dates.date(start) : '${dates.date(start)} – ${dates.date(end)}';
    return Semantics(
      button: true,
      label: '${context.l10n.removeFilter}, $formatted',
      excludeSemantics: true,
      onTap: onClear,
      child: OmiButton.toolbar(
        label: '$formatted ×',
        size: OmiButtonSize.compact,
        icon: Icons.calendar_month_outlined,
        onPressed: onClear,
      ),
    );
  }
}
