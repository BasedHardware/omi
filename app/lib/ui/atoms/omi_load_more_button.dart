import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiLoadMoreButton extends AdaptiveWidget {
  final int remaining;
  final VoidCallback onPressed;
  final bool loading;
  const OmiLoadMoreButton({
    super.key,
    required this.remaining,
    required this.onPressed,
    this.loading = false,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    if (loading) {
      return const CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
      );
    }

    return ElevatedButton.icon(
      onPressed: onPressed,
      icon: const Icon(Icons.expand_more, size: 18),
      label: Text(
        'Load More ($remaining remaining)',
        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
      ),
      style: ElevatedButton.styleFrom(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        foregroundColor: ResponsiveHelper.textSecondary,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: BorderSide(color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5), width: 1),
        ),
      ),
    );
  }
}
