import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:nooto_v2/theme/app_theme.dart';

class ShellTabBar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onTap;
  final List<String> labels;
  const ShellTabBar({
    super.key,
    required this.selectedIndex,
    required this.onTap,
    required this.labels,
  });

  static const _icons = <IconData>[
    FontAwesomeIcons.house,
    FontAwesomeIcons.message,
    FontAwesomeIcons.bookOpen,
    FontAwesomeIcons.calendarCheck,
    FontAwesomeIcons.tableCellsLarge,
  ];

  @override
  Widget build(BuildContext context) {
    final bottomSafe = MediaQuery.of(context).padding.bottom;
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.backgroundPrimary,
        border: Border(top: BorderSide(color: Colors.white10, width: 1)),
      ),
      padding: EdgeInsets.fromLTRB(12, 6, 12, bottomSafe + 4),
      child: Row(
        children: List.generate(_icons.length, (i) {
          final selected = i == selectedIndex;
          final color = selected ? AppColors.textPrimary : AppColors.textQuaternary;
          return Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
              onTap: () {
                HapticFeedback.lightImpact();
                onTap(i);
              },
              child: SizedBox(
                height: 52,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(_icons[i], color: color, size: 20),
                    const SizedBox(height: 4),
                    Text(
                      labels[i],
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w500,
                        color: color,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}
