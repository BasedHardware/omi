import 'package:flutter/material.dart';
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

    return Padding(
      padding: EdgeInsets.fromLTRB(16, isFirst ? 0 : 20, 16, 4),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          isToday
              ? 'Today'
              : isYesterday
                  ? 'Yesterday'
                  : dateTimeFormat('EEE MMM dd', date),
          style: const TextStyle(color: Colors.white, fontSize: 16),
        ),
      ),
    );
  }
}
