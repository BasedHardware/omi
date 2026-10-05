import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';

class UsageStatTile extends StatelessWidget {
  const UsageStatTile({super.key, required this.label, required this.value, required this.exactValue});
  final String label;
  final String value;
  final String exactValue;

  @override
  Widget build(BuildContext context) => Semantics(
        label: '$label, $exactValue',
        child: Tooltip(
          message: '$label: $exactValue',
          child: Container(
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
                color: OmiColors.groupedCard,
                borderRadius: OmiRadius.xlAll,
                border: Border.all(color: OmiColors.groupedBorder)),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: FittedBox(
                        alignment: Alignment.centerLeft,
                        fit: BoxFit.scaleDown,
                        child: Text(value, maxLines: 1, softWrap: false, style: OmiType.title1)),
                  ),
                ]),
          ),
        ),
      );
}
