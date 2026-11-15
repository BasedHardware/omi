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
    return Padding(
      padding: EdgeInsets.fromLTRB(20, isFirst ? 4 : 10, 16, 0),
      child: Semantics(
        header: true,
        child: Text(
          label ?? OmiDateFormat.of(context).dayHeader(date),
          style: OmiType.body.copyWith(fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}
