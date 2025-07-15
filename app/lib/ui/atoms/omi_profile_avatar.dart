import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiProfileAvatar extends AdaptiveWidget {
  final String? imageUrl;
  final double size;
  final String? fallbackText;
  final Color? backgroundColor;
  final Color? borderColor;
  final double borderWidth;
  final bool showShadow;
  final double? fontSize;
  final FontWeight? fontWeight;
  final Color? textColor;

  const OmiProfileAvatar({
    super.key,
    this.imageUrl,
    this.size = 120,
    this.fallbackText,
    this.backgroundColor,
    this.borderColor,
    this.borderWidth = 3,
    this.showShadow = true,
    this.fontSize,
    this.fontWeight,
    this.textColor,
  });

  @override
  Widget buildDesktop(BuildContext context) => _avatar();

  @override
  Widget buildMobile(BuildContext context) => _avatar();

  Widget _avatar() {
    final double radius = size / 2;
    final double calculatedFontSize = fontSize ?? size * 0.4;

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor ?? ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: borderColor ?? ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
          width: borderWidth,
        ),
        boxShadow: showShadow
            ? [
                BoxShadow(
                  color: (borderColor ?? ResponsiveHelper.purplePrimary).withValues(alpha: 0.2),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ]
            : null,
        image: imageUrl != null
            ? DecorationImage(
                image: NetworkImage(imageUrl!),
                fit: BoxFit.cover,
              )
            : null,
      ),
      child: imageUrl == null
          ? Center(
              child: Text(
                fallbackText ?? 'U',
                style: TextStyle(
                  color: textColor ?? ResponsiveHelper.purplePrimary,
                  fontSize: calculatedFontSize,
                  fontWeight: fontWeight ?? FontWeight.w700,
                ),
              ),
            )
          : null,
    );
  }
}
