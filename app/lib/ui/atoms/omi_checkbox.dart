import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiCheckbox extends AdaptiveWidget {
  final bool value;
  final ValueChanged<bool> onChanged;
  final Color activeColor;
  final double size;

  const OmiCheckbox({
    super.key,
    required this.value,
    required this.onChanged,
    this.activeColor = ResponsiveHelper.purplePrimary,
    this.size = 18,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    return InkWell(
      onTap: () => onChanged(!value),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: value ? activeColor : Colors.transparent,
          border: Border.all(
            color: value ? activeColor : ResponsiveHelper.textTertiary,
            width: 1.5,
          ),
          borderRadius: BorderRadius.circular(4),
        ),
        child: value
            ? const Icon(
                Icons.check,
                size: 10,
                color: Colors.white,
              )
            : null,
      ),
    );
  }
}
