import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/gen/fonts.gen.dart';

class WebSearchToggle extends StatelessWidget {
  final bool isEnabled;
  final ValueChanged<bool> onChanged;
  final bool isDesktop;

  const WebSearchToggle({
    super.key,
    required this.isEnabled,
    required this.onChanged,
    this.isDesktop = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.symmetric(
        horizontal: isDesktop ? 8 : 12,
        vertical: 4,
      ),
      decoration: BoxDecoration(
        color: isEnabled ? Colors.blue.withValues(alpha: 0.1) : Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isEnabled ? Colors.blue.withValues(alpha: 0.3) : Colors.white.withValues(alpha: 0.1),
          width: 1,
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => onChanged(!isEnabled),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: isDesktop ? 12 : 10,
            vertical: isDesktop ? 8 : 6,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                FontAwesomeIcons.globe,
                size: isDesktop ? 14 : 12,
                color: isEnabled ? Colors.blue : Colors.white70,
              ),
              SizedBox(width: isDesktop ? 8 : 6),
              Text(
                'Search web',
                style: TextStyle(
                  fontFamily: FontFamily.sFProDisplay,
                  fontSize: isDesktop ? 13 : 12,
                  fontWeight: FontWeight.w500,
                  color: isEnabled ? Colors.blue : Colors.white70,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
