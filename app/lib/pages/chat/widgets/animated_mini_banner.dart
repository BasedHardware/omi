import 'package:flutter/material.dart';

class AnimatedMiniBanner extends StatelessWidget implements PreferredSizeWidget {
  const AnimatedMiniBanner({super.key, required this.showAppBar, required this.child});

  final bool showAppBar;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      height: showAppBar ? kToolbarHeight : 0,
      duration: const Duration(milliseconds: 400),
      child: child,
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(30);
}
