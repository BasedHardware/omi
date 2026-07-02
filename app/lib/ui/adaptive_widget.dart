import 'package:flutter/widgets.dart';

abstract class AdaptiveWidget extends StatelessWidget {
  const AdaptiveWidget({super.key});

  /// Build for desktop (> 1100px).
  Widget buildDesktop(BuildContext context);

  /// Build for mobile (< 1100px). If the widget looks identical you can
  /// simply return the desktop tree here.
  Widget buildMobile(BuildContext context);

  @override
  Widget build(BuildContext context) {
    // sizeOf (not MediaQuery.of) so widgets don't rebuild on every viewInsets
    // change — e.g. each frame of the keyboard animation.
    final width = MediaQuery.sizeOf(context).width;
    if (width >= 1100) {
      return buildDesktop(context);
    }
    return buildMobile(context);
  }
}
