import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// A day group header in the conversation list: "Today", "Yesterday", "Wed, Sep 23", and the year
/// when it is not the current one (hub audit #16). Today gets a header too.
class DateListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;
  final String? label;

  const DateListItem({super.key, required this.date, required this.isFirst, this.label});

  @override
  Widget build(BuildContext context) {
    // The same box as a past day's summary header (DaySummaryHeader), so every day header in a list
    // is one height and the rows under Today start where they do under Yesterday.
    return Padding(
      padding: EdgeInsets.fromLTRB(20, isFirst ? 0 : 6, 16, 0),
      child: Semantics(
        header: true,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              label ?? OmiDateFormat.of(context).dayHeader(date),
              style: OmiType.body.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
        ),
      ),
    );
  }
}
