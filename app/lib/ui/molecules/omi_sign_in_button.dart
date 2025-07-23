import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSignInButton extends AdaptiveWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final bool enabled;
  final bool outline; // if true use outline style else filled secondary

  const OmiSignInButton({
    super.key,
    required this.icon,
    required this.label,
    this.onPressed,
    this.enabled = true,
    this.outline = true,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base(context);

  @override
  Widget buildMobile(BuildContext context) => _base(context);

  Widget _base(BuildContext context) {
    final responsive = ResponsiveHelper(context);
    final hovered = ValueNotifier(false);

    return ValueListenableBuilder<bool>(
      valueListenable: hovered,
      builder: (context, isHovered, _) {
        final borderColor = outline
            ? (isHovered && enabled
                ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                : ResponsiveHelper.backgroundTertiary)
            : Colors.transparent;

        final bgColor = outline
            ? (isHovered && enabled ? ResponsiveHelper.backgroundTertiary : ResponsiveHelper.backgroundSecondary)
            : ResponsiveHelper.purplePrimary;

        final fgColor = outline ? ResponsiveHelper.textPrimary : Colors.white;

        return MouseRegion(
          onEnter: (_) => hovered.value = true,
          onExit: (_) => hovered.value = false,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: enabled ? onPressed : null,
              borderRadius: BorderRadius.circular(responsive.radiusSmall),
              child: Container(
                width: double.infinity,
                padding: EdgeInsets.symmetric(
                  horizontal: responsive.spacing(baseSpacing: 24),
                  vertical: responsive.spacing(baseSpacing: 16),
                ),
                decoration: BoxDecoration(
                  color: outline ? bgColor : ResponsiveHelper.purplePrimary,
                  gradient: outline ? null : responsive.purpleGradient,
                  borderRadius: BorderRadius.circular(responsive.radiusSmall),
                  border: Border.all(color: borderColor, width: 1),
                  boxShadow: !outline && enabled
                      ? [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ]
                      : null,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(icon, color: enabled ? fgColor : ResponsiveHelper.textQuaternary, size: 20),
                    SizedBox(width: responsive.spacing(baseSpacing: 12)),
                    Text(
                      label,
                      style: responsive.labelMedium.copyWith(
                        color: enabled ? fgColor : ResponsiveHelper.textQuaternary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
