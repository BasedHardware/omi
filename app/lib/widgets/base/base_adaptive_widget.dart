import 'package:flutter/material.dart';

/// Base class for widgets that adapt their layout based on screen size
abstract class BaseAdaptiveWidget extends StatelessWidget {
  const BaseAdaptiveWidget({super.key});

  /// Check if current screen is mobile (< 1100px width)
  bool isMobile(BuildContext context) => MediaQuery.of(context).size.width < 1100;

  /// Check if current screen is desktop (>= 1100px width)
  bool isDesktop(BuildContext context) => !isMobile(context);

  /// Subclasses must implement mobile layout
  Widget buildMobile(BuildContext context);

  /// Subclasses must implement desktop layout
  Widget buildDesktop(BuildContext context);

  @override
  Widget build(BuildContext context) {
    return isMobile(context) ? buildMobile(context) : buildDesktop(context);
  }
}
