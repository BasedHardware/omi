import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';

class UsageStatTile extends StatelessWidget {
  const UsageStatTile(
      {super.key, required this.label, required this.value, required this.exactValue, required this.color});
  final String label;
  final String value;
  final String exactValue;
  final Color color;

  @override
  Widget build(BuildContext context) => Semantics(
        label: '$label, $exactValue',
        child: Tooltip(
          message: '$label: $exactValue',
          child: Container(
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
                color: OmiColors.surface1, borderRadius: OmiRadius.lgAll, border: Border.all(color: OmiColors.border)),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(children: [
                    Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                    const SizedBox(width: 6),
                    Expanded(
                        child: Text(label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.footnote
                                .copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500))),
                  ]),
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
