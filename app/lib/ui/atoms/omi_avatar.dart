import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiAvatar extends AdaptiveWidget {
  final String? imageUrl;
  final double size;
  final Widget? fallback;
  const OmiAvatar({
    super.key,
    this.imageUrl,
    this.size = 32,
    this.fallback,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(size / 2),
        image: imageUrl != null ? DecorationImage(image: NetworkImage(imageUrl!), fit: BoxFit.cover) : null,
        color: imageUrl == null ? ResponsiveHelper.backgroundTertiary : null,
      ),
      child: imageUrl == null
          ? fallback ?? const Icon(Icons.person, size: 16, color: ResponsiveHelper.textSecondary)
          : null,
    );
  }
}
