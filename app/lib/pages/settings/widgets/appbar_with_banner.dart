import 'package:flutter/material.dart';

class AppBarWithBanner extends StatelessWidget implements PreferredSizeWidget {
  const AppBarWithBanner({
    super.key,
    required this.showAppBar,
    required this.child,
    required this.appBar,
    this.bannerHeight = 30,
  });

  final bool showAppBar;
  final Widget child;
  final PreferredSizeWidget appBar;
  final double bannerHeight;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        appBar,
        AnimatedContainer(
          height: showAppBar ? bannerHeight : 0,
          duration: const Duration(milliseconds: 300),
          child: showAppBar ? child : const SizedBox.shrink(),
        ),
      ],
    );
  }

  @override
  Size get preferredSize => Size.fromHeight(
        appBar.preferredSize.height + (bannerHeight),
      );
}
