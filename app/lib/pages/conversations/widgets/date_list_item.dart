import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';

/// A day group header in the conversation list: "Today", "Yesterday", "Wed, Sep 23", and the year
/// when it is not the current one (hub audit #16). Today gets a header too.
class DateListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;
  final bool collapsed;
  final VoidCallback? onToggle;

  const DateListItem({
    super.key,
    required this.date,
    required this.isFirst,
    this.collapsed = false,
    this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, isFirst ? 4 : 10, 16, 0),
      child: MergeSemantics(
        child: Row(
          children: [
            Expanded(
              child: Semantics(
                header: true,
                child: Text(
                  OmiDateFormat.of(context).dayHeader(date),
                  style: OmiType.body.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
            ),
            // Merge localized day/action labels without hardcoding their word order.
            if (onToggle != null)
              Semantics(
                expanded: !collapsed,
                child: OmiIconButton(
                  key: ValueKey('collapse_day_${DateUtils.dateOnly(date).toIso8601String()}'),
                  label: collapsed ? AppLocalizations.of(context).expand : AppLocalizations.of(context).collapseAction,
                  onPressed: onToggle,
                  icon: Icon(collapsed ? Icons.expand_more : Icons.expand_less, size: 20),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
