import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class DateListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;

  const DateListItem({super.key, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    var now = DateTime.now();
    var yesterday = now.subtract(const Duration(days: 1));
    var isToday = date.month == now.month && date.day == now.day && date.year == now.year;
    var isYesterday = date.month == yesterday.month && date.day == yesterday.day && date.year == yesterday.year;

    // Today used to render nothing, which left "Yesterday" looking like a third
    // top-level section and implied — without saying so — that the rows above it
    // were today's. Every group is labelled now.
    final label = isToday
        ? context.l10n.today
        : isYesterday
            ? context.l10n.yesterday
            : dateTimeFormat('MMM dd', date, locale: Localizations.localeOf(context).languageCode);

    return Padding(
      // Small, muted and close to the rows it labels — a divider inside the
      // list, not a heading competing with the section titles.
      padding: EdgeInsets.fromLTRB(16, isFirst ? 0 : 24, 16, 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            label.toUpperCase(),
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.45),
              fontSize: 12,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.8,
            ),
          ),
        ],
      ),
    );
  }
}
