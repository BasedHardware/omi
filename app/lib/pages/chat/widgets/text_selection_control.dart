import 'package:flutter/material.dart';

class IOSTextSelectionControls extends MaterialTextSelectionControls {
  final Color handleColor;

  IOSTextSelectionControls({required this.handleColor});

  @override
  Widget buildHandle(
    BuildContext context,
    TextSelectionHandleType type,
    double textHeight, [
    VoidCallback? onTap,
  ]) {
    const double circleSize = 8.0;
    const double lineHeight = 20.0;
    const double lineWidth = 2.0;

    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: circleSize,
        height: type == TextSelectionHandleType.collapsed ? circleSize : lineHeight + circleSize,
        child: Stack(
          children: [
            if (type != TextSelectionHandleType.collapsed)
              Positioned(
                left: (circleSize - lineWidth) / 2,
                top: type == TextSelectionHandleType.left ? circleSize / 2 : 0,
                child: Container(
                  width: lineWidth,
                  height: lineHeight,
                  color: handleColor,
                ),
              ),
            Positioned(
              top: type == TextSelectionHandleType.right ? lineHeight : 0,
              child: Container(
                width: circleSize,
                height: circleSize,
                decoration: BoxDecoration(
                  color: handleColor,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.2),
                      blurRadius: 2,
                      offset: const Offset(0, 1),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Offset getHandleAnchor(TextSelectionHandleType type, double textLineHeight) {
    const double circleSize = 12.0;
    const double lineHeight = 20.0;

    switch (type) {
      case TextSelectionHandleType.left:
        return const Offset(circleSize / 2, lineHeight + circleSize - 10);
      case TextSelectionHandleType.right:
        return const Offset(circleSize / 2 - 3, circleSize + 2);
      case TextSelectionHandleType.collapsed:
        return const Offset(circleSize / 2, circleSize / 2);
    }
  }
}
