import 'package:flutter/material.dart';

class AnimatedMiniBanner extends StatelessWidget implements PreferredSizeWidget {
  const AnimatedMiniBanner({super.key, required this.showAppBar, required this.child, this.height = 30});

  final bool showAppBar;
  final Widget child;
  final double height;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      height: showAppBar ? kToolbarHeight : 0,
      duration: const Duration(milliseconds: 300),
      child: child,
    );
  }

  @override
  Size get preferredSize => Size.fromHeight(height);
}
