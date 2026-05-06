import 'package:flutter/material.dart';

/// Generous section header.
///
/// Single line title at left, optional `View all ›` text-link at right.
/// Lots of vertical breathing room either side so the page doesn't read as
/// densely-packed product cards stacked on top of each other.
class SectionHeader extends StatelessWidget {
  final String title;
  final VoidCallback? onViewAll;

  const SectionHeader({super.key, required this.title, this.onViewAll});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 36, 24, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: Colors.white,
                letterSpacing: -0.4,
                height: 1.2,
              ),
            ),
          ),
          if (onViewAll != null)
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onViewAll,
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 4, horizontal: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'See all',
                      style: TextStyle(
                        fontSize: 14,
                        color: Color(0xFFB8B6C5),
                        fontWeight: FontWeight.w500,
                        letterSpacing: -0.1,
                      ),
                    ),
                    SizedBox(width: 2),
                    Icon(Icons.chevron_right_rounded, color: Color(0xFFB8B6C5), size: 18),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
