import 'package:flutter/cupertino.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Two to four mutually exclusive views of one list or chart (Today · Month · Year, All · Pending
/// · Synced): the iOS sliding control in the Settings look, an [OmiColors.iconTile] track with a
/// thumb that stands out from it (white in light mode, [OmiColors.surface3] in dark), full width,
/// 44 pt segments whose labels never wrap.
class OmiSegmentedControl<T extends Object> extends StatelessWidget {
  const OmiSegmentedControl({super.key, required this.value, required this.segments, required this.onChanged});

  final T value;

  /// Each option and its label, in display order.
  final Map<T, String> segments;

  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: CupertinoSlidingSegmentedControl<T>(
        groupValue: value,
        backgroundColor: OmiColors.iconTile,
        thumbColor: OmiColors.active == OmiPalette.light ? OmiColors.groupedCard : OmiColors.surface3,
        onValueChanged: (next) {
          if (next != null) onChanged(next);
        },
        children: {
          for (final entry in segments.entries)
            entry.key: SizedBox(
              height: 44,
              child: Center(
                child: Text(
                  entry.value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textPrimary),
                ),
              ),
            ),
        },
      ),
    );
  }
}
